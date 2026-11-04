"""v1.12 GitHub source (W3): one repository, read through a fake `gh`, never written to."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from organism_sdk.work.domain import Addressed
from organism_sdk.work.sources.github import GhCli, GhError, GitHubSource, RoundReport
from organism_sdk.work.store import WorkStore

REPO = "acme/widgets"
LOGIN = "organism-agent"
FAKE_GH = Path(__file__).with_name("fake_gh.py")
SOURCE_KEY = f"github:{REPO}"
NOTIFICATIONS = f"repos/{REPO}/notifications"
ISSUE_7 = f"repos/{REPO}/issues/7/comments"
ISSUE_8 = f"repos/{REPO}/issues/8/comments"
ISSUE_12 = f"repos/{REPO}/issues/12/comments"
REVIEW_12 = f"repos/{REPO}/pulls/12/comments"
T10 = "2026-11-04T10:00:00Z"
T11 = "2026-11-04T11:00:00Z"


def issue_note(note_id: str, number: int, updated: str) -> dict[str, Any]:
    return {
        "id": note_id,
        "updated_at": updated,
        "subject": {"type": "Issue", "url": f"https://api.github.com/repos/{REPO}/issues/{number}"},
    }


def pull_note(note_id: str, number: int, updated: str) -> dict[str, Any]:
    return {
        "id": note_id,
        "updated_at": updated,
        "subject": {
            "type": "PullRequest",
            "url": f"https://api.github.com/repos/{REPO}/pulls/{number}",
        },
    }


def comment(
    comment_id: int, login: str, body: str, created: str, kind: str = "User"
) -> dict[str, Any]:
    return {
        "id": comment_id,
        "user": {"login": login, "type": kind},
        "body": body,
        "created_at": created,
        "updated_at": created,
    }


class FakeGh:
    """Writes the fixture the fake `gh` serves from, and reads back the calls it logged."""

    def __init__(self, directory: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.fixture = directory / "fixture.json"
        self.log = directory / "calls.log"
        monkeypatch.setenv("FAKE_GH_FIXTURE", str(self.fixture))
        monkeypatch.setenv("FAKE_GH_LOG", str(self.log))
        self.cli = GhCli(command=(sys.executable, str(FAKE_GH)))

    def serve(self, responses: dict[str, Any]) -> None:
        self.fixture.write_text(json.dumps({"responses": responses}), encoding="utf-8")

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeGh:
    return FakeGh(tmp_path, monkeypatch)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[WorkStore]:
    with WorkStore(tmp_path / "work.sqlite") as handle:
        yield handle


def serve_round(fake: FakeGh) -> None:
    """One issue and one pull request, with a mention, a bot, the agent's own words and a review."""
    fake.serve(
        {
            NOTIFICATIONS: {
                "pages": [[issue_note("1", 7, T10)], [pull_note("2", 12, T11)]],
            },
            ISSUE_7: {
                "pages": [
                    [
                        comment(
                            101, "alice", f"@{LOGIN} please fix the build", "2026-11-04T10:01:00Z"
                        ),
                        comment(102, LOGIN, "on it", "2026-11-04T10:02:00Z"),
                        comment(103, "ci-bot", "build ok", "2026-11-04T10:03:00Z", kind="Bot"),
                    ]
                ],
            },
            ISSUE_12: {"pages": [[]]},
            REVIEW_12: {
                "pages": [[comment(201, "bob", "nit: rename this", "2026-11-04T11:01:00Z")]],
            },
        }
    )


def test_comments_become_triggers_with_their_threads_and_addressing(
    fake: FakeGh, store: WorkStore
) -> None:
    serve_round(fake)
    report = GitHubSource(REPO, login=LOGIN, gh=fake.cli).poll(store)

    assert report == RoundReport(new_triggers=3, failed={}, cursor=T11)
    issue = store.triggers_in_thread(f"github:{REPO}#7")
    assert [(item.actor, item.human, item.addressed) for item in issue] == [
        ("alice", True, Addressed.MENTION),
        ("ci-bot", False, Addressed.NONE),
    ]
    review = store.triggers_in_thread(f"github:{REPO}#12")
    assert [item.id for item in review] == ["github:review:201"]


def test_the_cursor_is_stored_and_the_agents_own_comments_are_not_triggers(
    fake: FakeGh, store: WorkStore
) -> None:
    serve_round(fake)
    GitHubSource(REPO, login=LOGIN, gh=fake.cli).poll(store)

    assert store.cursor(SOURCE_KEY) == T11
    assert all(item.actor != LOGIN for item in store.triggers_in_thread(f"github:{REPO}#7"))


def test_a_second_poll_asks_only_for_what_is_newer_and_stores_nothing_twice(
    fake: FakeGh, store: WorkStore
) -> None:
    serve_round(fake)
    source = GitHubSource(REPO, login=LOGIN, gh=fake.cli)
    source.poll(store)
    second = source.poll(store)

    assert second == RoundReport(new_triggers=0, failed={}, cursor=T11)
    assert store.trigger_count() == 3
    notification_calls = [call for call in fake.calls() if call[2].startswith(NOTIFICATIONS)]
    assert "since=" in notification_calls[-1][2]


def test_a_failed_item_keeps_its_own_error_and_holds_the_cursor_until_it_recovers(
    fake: FakeGh, store: WorkStore
) -> None:
    notes = [issue_note("1", 7, T10), issue_note("2", 8, T11)]
    carol = comment(301, "carol", "hello", "2026-11-04T11:00:00Z")
    fake.serve(
        {
            NOTIFICATIONS: {"pages": [notes]},
            ISSUE_7: {"error": "HTTP 500: upstream failed"},
            ISSUE_8: {"pages": [[carol]]},
        }
    )
    source = GitHubSource(REPO, login=LOGIN, gh=fake.cli)

    first = source.poll(store)

    assert first.new_triggers == 1
    assert list(first.failed) == ["thread:1"]
    assert "HTTP 500" in first.failed["thread:1"]
    assert first.cursor == T10
    assert store.source_errors(SOURCE_KEY) == first.failed

    fake.serve(
        {
            NOTIFICATIONS: {"pages": [notes]},
            ISSUE_7: {"pages": [[comment(101, "alice", "again", "2026-11-04T10:01:00Z")]]},
            ISSUE_8: {"pages": [[carol]]},
        }
    )
    second = source.poll(store)

    assert second == RoundReport(new_triggers=1, failed={}, cursor=T11)
    assert store.source_errors(SOURCE_KEY) == {}
    assert store.trigger_count() == 2


def test_a_failed_notifications_listing_fails_the_round_and_stores_nothing(
    fake: FakeGh, store: WorkStore
) -> None:
    fake.serve({NOTIFICATIONS: {"error": "HTTP 503: unavailable"}})

    with pytest.raises(GhError, match="HTTP 503"):
        GitHubSource(REPO, login=LOGIN, gh=fake.cli).poll(store)
    assert store.cursor(SOURCE_KEY) is None
    assert store.trigger_count() == 0


def test_every_call_stays_inside_the_one_repository_and_uses_argv_only(
    fake: FakeGh, store: WorkStore
) -> None:
    serve_round(fake)
    GitHubSource(REPO, login=LOGIN, gh=fake.cli).poll(store)

    calls = fake.calls()
    assert calls
    assert all(call[:2] == ["api", "--paginate"] for call in calls)
    assert all(call[2].startswith(f"repos/{REPO}/") for call in calls)


@pytest.mark.parametrize("repo", ["acme", "acme/widgets; rm -rf /", "../acme/widgets"])
def test_a_repository_name_that_is_not_owner_and_name_is_refused(repo: str) -> None:
    with pytest.raises(ValueError, match="owner/name"):
        GitHubSource(repo, login=LOGIN)


def test_a_login_that_is_not_a_github_login_is_refused() -> None:
    with pytest.raises(ValueError, match="GitHub login"):
        GitHubSource(REPO, login="bad login")


@pytest.mark.skipif(
    not os.environ.get("ORGANISM_GH_SMOKE_REPO"),
    reason="opt-in: set ORGANISM_GH_SMOKE_REPO to a test repository to poll it live",
)
def test_a_live_poll_of_a_test_repository(tmp_path: Path) -> None:
    repo = os.environ["ORGANISM_GH_SMOKE_REPO"]
    login = os.environ.get("ORGANISM_GH_SMOKE_LOGIN", LOGIN)
    with WorkStore(tmp_path / "work.sqlite") as store:
        report = GitHubSource(repo, login=login).poll(store)
    assert isinstance(report, RoundReport)
