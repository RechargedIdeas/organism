"""The GitHub source, read only (v1.12 W3). Design record: docs/v1.12/WORK_AGENT.md.

It reads one repository's notifications, and the comments on the Issues and pull requests they
name, and turns each new comment into a Trigger. It never writes to GitHub, and the agent's own
comments are never Triggers. Reads go through `gh api` with argv only, never through a shell, so
a repository name cannot become a command.

The cursor is the newest notification time that is safe to keep. An item that fails keeps its own
error, and the cursor stops before its notification, so the item is read again next round. Items
read again are de-duplicated by id at intake. The cursor and the errors commit with the round.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from organism_sdk.work.domain import Addressed, Trigger, thread_key
from organism_sdk.work.store import WorkStore

SOURCE = "github"
TIMEOUT_S = 60.0
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_LOGIN = re.compile(r"[A-Za-z0-9-]+")
_ITEM_KINDS = ("Issue", "PullRequest")


class GhError(RuntimeError):
    """A `gh api` call failed, or its answer was not a list of objects."""


@dataclass(frozen=True)
class GhCli:
    """Runs `gh api` with argv only, never through a shell. `command` is the program to run."""

    command: tuple[str, ...] = ("gh",)
    timeout_s: float = TIMEOUT_S

    def items(self, endpoint: str) -> list[dict[str, Any]]:
        """Every item of a GET endpoint, across all of its pages."""
        argv = [*self.command, "api", "--paginate", endpoint]
        try:
            # argv only, never through a shell: a repository name cannot become a command.
            done = subprocess.run(
                argv,
                capture_output=True,
                encoding="utf-8",
                check=False,
                timeout=self.timeout_s,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise GhError(f"gh api {endpoint}: {error}") from None
        if done.returncode != 0:
            raise GhError(f"gh api {endpoint}: exit {done.returncode}: {done.stderr.strip()[:300]}")
        return _items(endpoint, done.stdout)


@dataclass(frozen=True)
class RoundReport:
    """What one poll did: its new Triggers, its failed items with their errors, and the cursor."""

    new_triggers: int
    failed: Mapping[str, str]
    cursor: str | None


class GitHubSource:
    """Reads one repository's notifications and the comments they point at."""

    def __init__(self, repo: str, *, login: str, gh: GhCli | None = None) -> None:
        if not _REPO.fullmatch(repo):
            raise ValueError(f"repo must be owner/name, got {repo!r}")
        if not _LOGIN.fullmatch(login):
            raise ValueError(f"login must be a GitHub login, got {login!r}")
        self.repo = repo
        self.login = login
        self.gh = gh or GhCli()
        self.cursor_key = f"{SOURCE}:{repo}"

    def poll(self, store: WorkStore) -> RoundReport:
        """Run one round: read what is new, store it with the cursor, and keep each failure's error.

        A failed notifications listing fails the whole round and stores nothing. A failed item
        does not: its error is kept, and the round goes on.
        """
        cursor = store.cursor(self.cursor_key)
        notes = sorted(self._notifications(cursor), key=_updated_at)
        triggers: list[Trigger] = []
        failed: dict[str, str] = {}
        succeeded: list[str] = []
        held: str | None = None
        for note in notes:
            item = f"thread:{note['id']}"
            try:
                found = self._triggers(note, cursor)
            except GhError as error:
                failed[item] = str(error)
                held = held or _updated_at(note)
            else:
                triggers.extend(found)
                succeeded.append(item)
        cursor_after = held or (_updated_at(notes[-1]) if notes else cursor)
        new = 0
        with store.transaction():
            if cursor_after is not None:
                new = store.commit_round(self.cursor_key, triggers, cursor=cursor_after)
            store.record_source_outcomes(self.cursor_key, failed=failed, succeeded=succeeded)
        return RoundReport(new_triggers=new, failed=failed, cursor=cursor_after)

    def _notifications(self, cursor: str | None) -> list[dict[str, Any]]:
        query: dict[str, str] = {"all": "true"}
        if cursor is not None:
            query["since"] = cursor
        return self.gh.items(_endpoint(f"repos/{self.repo}/notifications", query))

    def _triggers(self, note: Mapping[str, Any], cursor: str | None) -> list[Trigger]:
        """The new comments on the item one notification names. Other kinds of thread give none."""
        subject = note.get("subject") or {}
        if subject.get("type") not in _ITEM_KINDS:
            return []
        number = _number(note)
        thread = thread_key(SOURCE, f"{self.repo}#{number}")
        query: dict[str, str] = {} if cursor is None else {"since": cursor}
        paths = [("comment", f"repos/{self.repo}/issues/{number}/comments")]
        if subject["type"] == "PullRequest":
            paths.append(("review", f"repos/{self.repo}/pulls/{number}/comments"))
        found: list[Trigger] = []
        for kind, path in paths:
            for item in self.gh.items(_endpoint(path, query)):
                trigger = self._trigger(kind, item, thread)
                if trigger is not None:
                    found.append(trigger)
        return found

    def _trigger(self, kind: str, item: Mapping[str, Any], thread: str) -> Trigger | None:
        author = item.get("user") or {}
        login = author.get("login")
        if login == self.login:
            return None
        body = str(item.get("body") or "")
        mention = re.search(rf"@{re.escape(self.login)}(?![\w-])", body, re.IGNORECASE)
        return Trigger(
            id=f"{SOURCE}:{kind}:{item['id']}",
            source=SOURCE,
            thread=thread,
            actor=login,
            human=author.get("type") != "Bot",
            addressed=Addressed.MENTION if mention else Addressed.NONE,
            at=str(item["created_at"]),
            text=body,
        )


def _endpoint(path: str, query: Mapping[str, str]) -> str:
    return f"{path}?{urlencode(query)}" if query else path


def _updated_at(note: Mapping[str, Any]) -> str:
    return str(note["updated_at"])


def _number(note: Mapping[str, Any]) -> int:
    """The number of the Issue or pull request a notification names, read from its API URL."""
    try:
        return int(str(note["subject"]["url"]).rsplit("/", 1)[-1])
    except (KeyError, TypeError, ValueError) as error:
        raise GhError(f"notification {note.get('id')}: no item number") from error


def _items(endpoint: str, text: str) -> list[dict[str, Any]]:
    """Read the JSON arrays that `gh api --paginate` prints one after another, one per page."""
    decoder = json.JSONDecoder()
    items: list[dict[str, Any]] = []
    position = _skip_space(text, 0)
    while position < len(text):
        try:
            page, position = decoder.raw_decode(text, position)
        except json.JSONDecodeError as error:
            raise GhError(f"gh api {endpoint}: output is not JSON: {error}") from None
        if not isinstance(page, list) or not all(isinstance(item, dict) for item in page):
            raise GhError(f"gh api {endpoint}: expected a list of objects")
        items.extend(page)
        position = _skip_space(text, position)
    return items


def _skip_space(text: str, position: int) -> int:
    while position < len(text) and text[position].isspace():
        position += 1
    return position
