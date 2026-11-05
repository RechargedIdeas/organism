"""v1.12 work agent, hardening: the error and edge paths the other suites do not reach in-process.

Each test names a branch that a coverage run showed unexecuted. They use no network, no real `gh`,
and no real executor. Test keys only; the approver key never enters the repo (decision S1)."""

from __future__ import annotations

import contextlib
import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from organism_sdk.sandbox.policy import SandboxPolicy
from organism_sdk.work import operator
from organism_sdk.work.domain import Mandate, Strength, Ticket, Via
from organism_sdk.work.driver import revalidate_notices
from organism_sdk.work.executors import end_process_group
from organism_sdk.work.executors.process import ProcessExecutor, Slots
from organism_sdk.work.governance import NOTICE
from organism_sdk.work.policy import AcceptMode, AdmissionRow, Cell, Policy, Rule, SourcePolicy
from organism_sdk.work.sources.github import GhCli, GhError, GitHubSource, _items
from organism_sdk.work.store import DEFAULT_STORE, STORE_ENV, WorkStore, default_store_path

REPO = "acme/widgets"
LOGIN = "organism-agent"
NOTIFICATIONS = f"repos/{REPO}/notifications"
T10 = "2026-11-04T10:00:00Z"


def mandate(*, rules: tuple[str, ...] = ("ci-fix",), source: str = "github") -> Mandate:
    return Mandate(
        policy_version="sha256:test",
        strength=Strength.EXPLICIT,
        via=Via.ADDRESSED,
        source=source,
        row="repo",
        sender="alice",
        rules=rules,
    )


def policy() -> Policy:
    github = SourcePolicy(
        source="github",
        allowed=frozenset({"alice"}),
        rows={"repo": AdmissionRow(unlisted_addressed=Cell.EXPLICIT)},
    )
    rules = (Rule(id="ci-fix", instruction="fix CI", pattern="CI"),)
    return Policy(mode=AcceptMode.OBSERVE, rules=rules, sources=(github,))


@pytest.fixture
def store(tmp_path: Path) -> Iterator[WorkStore]:
    with WorkStore(tmp_path / "work.sqlite") as handle:
        yield handle


# The operator's listing of open Tickets, read in-process (the CLI runs it in a subprocess).


def test_tickets_lists_only_the_open_tickets_with_their_thread_and_rules(store: WorkStore) -> None:
    store.save_ticket(Ticket(id="t-open", mandate=mandate(), thread="github:acme/widgets#7"))
    store.save_ticket(Ticket(id="t-done", mandate=mandate(), ended=True))
    rows = operator.tickets(store)
    assert [row["id"] for row in rows] == ["t-open"]
    assert rows[0]["thread"] == "github:acme/widgets#7"
    assert rows[0]["source"] == "github"
    assert rows[0]["rules"] == ["ci-fix"]
    assert rows[0]["latest_report"] is None


# The store's guards.


def test_an_unknown_policy_version_cannot_be_made_active(store: WorkStore) -> None:
    with pytest.raises(KeyError):
        store.set_active_policy("sha256:not-stored")


def test_retry_makes_every_waiting_effect_due_or_only_one_kind(store: WorkStore) -> None:
    store.enqueue("alpha", "t1", {"a": 1})
    store.enqueue("beta", "t2", {"b": 2})
    assert store.retry_effects() == 2
    assert store.retry_effects("alpha") == 1


def test_an_effect_payload_that_is_not_an_object_is_refused_when_read(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    with WorkStore(path) as store:
        store.enqueue("alpha", "t1", {"a": 1})
    with contextlib.closing(sqlite3.connect(path)) as raw:
        raw.execute("UPDATE effects SET payload = '[1]'")
        raw.commit()
    with WorkStore(path) as store, pytest.raises(TypeError):
        store.pending_effects()


def test_the_store_path_comes_from_the_environment_or_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chosen = tmp_path / "chosen.sqlite"
    monkeypatch.setenv(STORE_ENV, str(chosen))
    assert default_store_path() == chosen
    monkeypatch.delenv(STORE_ENV)
    assert default_store_path() == Path(DEFAULT_STORE)


# Settling a Policy notice (W9): a notice for a Ticket that has ended, and one whose Mandate still
# stands on a Ticket that had been marked for a person.


def test_a_notice_for_an_ended_ticket_is_dropped_without_asking_a_person(store: WorkStore) -> None:
    store.save_ticket(Ticket(id="t-ended", mandate=mandate(), ended=True))
    store.enqueue(NOTICE, "t-ended", {"policy": "sha256:test"})
    assert revalidate_notices(store, policy()) == []
    assert [effect for effect in store.pending_effects() if effect.kind == NOTICE] == []


def test_a_notice_whose_mandate_still_stands_clears_the_attention_it_had(store: WorkStore) -> None:
    store.save_ticket(Ticket(id="t-ci", mandate=mandate(), attention=True))
    store.enqueue(NOTICE, "t-ci", {"policy": "sha256:test"})
    assert revalidate_notices(store, policy()) == []
    settled = store.ticket("t-ci")
    assert settled is not None and settled.attention is False
    assert [effect for effect in store.pending_effects() if effect.kind == NOTICE] == []


# The GitHub source's error and edge paths, without a real `gh`.


def test_a_gh_that_cannot_be_started_is_a_gh_error(tmp_path: Path) -> None:
    cli = GhCli(command=(str(tmp_path / "no-such-gh"),))
    with pytest.raises(GhError, match="gh api"):
        cli.items(NOTIFICATIONS)


def test_pages_of_json_are_read_one_after_another() -> None:
    assert _items("x", '[{"a": 1}]\n[{"a": 2}, {"a": 3}]\n') == [{"a": 1}, {"a": 2}, {"a": 3}]


def test_output_that_is_not_json_is_a_gh_error() -> None:
    with pytest.raises(GhError, match="not JSON"):
        _items("repos/x/notifications", "not json")


def test_output_that_is_not_a_list_of_objects_is_a_gh_error() -> None:
    with pytest.raises(GhError, match="expected a list of objects"):
        _items("repos/x/notifications", '{"a": 1}')
    with pytest.raises(GhError, match="expected a list of objects"):
        _items("repos/x/notifications", "[1, 2]")


class _NoGh:
    """A `gh` that serves nothing. Every call is answered with an empty list."""

    def items(self, endpoint: str) -> list[dict[str, Any]]:
        return []


def test_a_notification_about_another_kind_of_thread_gives_no_triggers(store: WorkStore) -> None:
    class Notes(_NoGh):
        def items(self, endpoint: str) -> list[dict[str, Any]]:
            if endpoint.startswith(NOTIFICATIONS):
                return [
                    {
                        "id": "9",
                        "updated_at": T10,
                        "subject": {"type": "Release", "url": f"https://x/repos/{REPO}/releases/3"},
                    }
                ]
            return []

    report = GitHubSource(REPO, login=LOGIN, gh=Notes()).poll(store)  # type: ignore[arg-type]
    assert report.new_triggers == 0
    assert report.failed == {}


def test_a_notification_without_an_item_number_is_a_failed_item(store: WorkStore) -> None:
    class Notes(_NoGh):
        def items(self, endpoint: str) -> list[dict[str, Any]]:
            if endpoint.startswith(NOTIFICATIONS):
                return [{"id": "9", "updated_at": T10, "subject": {"type": "Issue"}}]
            return []

    report = GitHubSource(REPO, login=LOGIN, gh=Notes()).poll(store)  # type: ignore[arg-type]
    assert any("no item number" in str(text) for text in report.failed.values())


# The executor's refusal, asked on its own, and the process group on Windows.


def test_blocked_reason_names_a_blocked_program_and_a_missing_containment(tmp_path: Path) -> None:
    def executor(argv: list[str], gap: str | None) -> ProcessExecutor:
        return ProcessExecutor(
            tmp_path,
            argv=argv,
            slots=Slots(2),
            policy=SandboxPolicy(timeout_s=5, label="hardening"),
            containment_check=lambda: gap,
        )

    assert "blocked" in str(executor(["sudo", "x"], None).blocked_reason())
    assert executor(["claude", "-p"], "no containment here").blocked_reason() == (
        "no containment here"
    )
    assert executor(["claude", "-p"], None).blocked_reason() is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows has no process groups")
def test_on_windows_there_is_no_process_group_to_end() -> None:
    assert end_process_group(4242) is False
