"""v1.12 W7, the operator's surface: the view it shows, the changes it may make, and the CLI."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from organism_sdk.cli import main
from organism_sdk.signing import TrustStore, public_key_for, sign
from organism_sdk.work import operator
from organism_sdk.work.channels import queue_reply
from organism_sdk.work.domain import (
    Addressed,
    Assignment,
    AssignmentState,
    Mandate,
    Report,
    Strength,
    Ticket,
    Trigger,
    Via,
)
from organism_sdk.work.governance import adopt, policy_payload
from organism_sdk.work.policy import AcceptMode, AdmissionRow, Policy, Rule, SourcePolicy
from organism_sdk.work.store import ReceiptStatus, WorkStore

APPROVER = bytes([1]) * 32  # test key only
TRUST = TrustStore(approvers=frozenset({public_key_for(APPROVER)}))
THREAD = "github:octo/cat#1"


class Clock:
    def __init__(self, now: float = 10_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def policy(*, instruction: str = "fix CI") -> Policy:
    part = SourcePolicy(
        source="github",
        allowed=frozenset({"alice"}),
        rows={"repo": AdmissionRow()},
    )
    rule = Rule(id="ci-fix", instruction=instruction, pattern="CI")
    return Policy(mode=AcceptMode.OBSERVE, rules=(rule,), sources=(part,))


def signed(pol: Policy) -> bytes:
    return sign(APPROVER, policy_payload(pol.version))


def ticket(
    store: WorkStore,
    ticket_id: str,
    *,
    report: Report | None = None,
    ended: bool = False,
    thread: str | None = None,
) -> None:
    mandate = Mandate(
        policy_version="sha256:test",
        strength=Strength.EXPLICIT,
        via=Via.ADDRESSED,
        source="github",
        row="repo",
        sender="alice",
        rules=("ci-fix",),
    )
    assignment = Assignment(id=f"a-{ticket_id}", ticket_id=ticket_id, state=AssignmentState.RUNNING)
    store.save_ticket(
        Ticket(
            id=ticket_id,
            mandate=mandate,
            ended=ended,
            assignment=assignment,
            latest_report=report,
            thread=thread,
        )
    )


def failing(_: Mapping[str, Any]) -> None:
    raise RuntimeError("boom")


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "work.sqlite"


@pytest.fixture
def store(path: Path, clock: Clock) -> Iterator[WorkStore]:
    with WorkStore(path, clock=clock) as handle:
        yield handle


def test_status_counts_the_stages_and_the_policy(store: WorkStore) -> None:
    ticket(store, "t-working")
    ticket(store, "t-blocked", report=Report.BLOCKED)
    report = operator.status(store)
    assert report["open_tickets"] == 2
    assert report["stages"] == {"person/blocked": 1, "working": 1}
    assert report["policy"] is None
    assert report["paused"] is False


def test_attention_lists_the_tickets_waiting_on_a_person(store: WorkStore) -> None:
    ticket(store, "t-working")
    ticket(store, "t-blocked", report=Report.BLOCKED)
    ids = [item["id"] for item in operator.attention(store) if item["kind"] == "ticket"]
    assert ids == ["t-blocked"]


def test_attention_lists_notices_failing_effects_and_failing_sources(
    store: WorkStore,
) -> None:
    pol = policy()
    adopt(store, pol, signature=signed(pol), trust=TRUST)
    ticket(store, "t-ci")
    changed = policy(instruction="fix CI harder")
    adopt(store, changed, signature=signed(changed), trust=TRUST)
    store.enqueue("broken", "x", {})
    store.run_due({"broken": failing})
    store.record_source_outcomes("github:octo/cat", failed={"thread:9": "HTTP 500"}, succeeded=[])
    kinds = sorted(item["kind"] for item in operator.attention(store))
    assert kinds == ["effect", "policy_notice", "source"]


def test_stop_ends_the_ticket_and_drops_its_waiting_replies(store: WorkStore) -> None:
    ticket(store, "t1", thread=THREAD)
    queue_reply(store, ticket_id="t1", receipt_id="r1", conversation=THREAD, text="later")
    operator.stop(store, "t1")
    stopped = store.ticket("t1")
    assert stopped is not None and stopped.ended is True
    receipt = store.receipt("r1")
    assert receipt is not None
    assert (receipt.status, receipt.reason) == (ReceiptStatus.DROPPED, "stopped")
    assert [effect.kind for effect in store.pending_effects()] == []


def test_a_stopped_or_unknown_ticket_cannot_be_stopped_again(store: WorkStore) -> None:
    ticket(store, "t1")
    operator.stop(store, "t1")
    with pytest.raises(KeyError):
        operator.stop(store, "t1")
    with pytest.raises(KeyError):
        operator.stop(store, "nope")


def test_pause_holds_every_effect_until_resume(store: WorkStore) -> None:
    seen: list[str] = []
    handlers: dict[str, Callable[[Mapping[str, Any]], None]] = {
        "note": lambda _: seen.append("ran")
    }
    store.enqueue("note", "n1", {})
    operator.pause(store)
    assert store.run_due(handlers).completed == 0
    operator.resume(store)
    assert store.run_due(handlers).completed == 1
    assert seen == ["ran"]


def test_retry_makes_a_failing_effect_due_now(store: WorkStore, clock: Clock) -> None:
    store.enqueue("note", "n1", {})
    store.run_due({"note": failing})  # fails and waits out its backoff
    handlers: dict[str, Callable[[Mapping[str, Any]], None]] = {"note": lambda _: None}
    assert store.run_due(handlers).completed == 0
    assert operator.retry(store, "note") == 1
    assert store.run_due(handlers).completed == 1


def test_evaluate_needs_a_policy_in_force(store: WorkStore) -> None:
    with pytest.raises(operator.NoActivePolicy):
        operator.evaluate_triggers(store, row="repo")


def test_evaluate_decides_under_the_policy_in_force(store: WorkStore) -> None:
    pol = policy()
    adopt(store, pol, signature=signed(pol), trust=TRUST)
    store.receive(
        Trigger(
            id="m1",
            source="github",
            thread=THREAD,
            actor="alice",
            human=True,
            addressed=Addressed.MENTION,
            at="2026-11-04T00:00:00Z",
            text="please look at CI",
        )
    )
    report = operator.evaluate_triggers(store, row="repo")
    assert (report.decided, report.unavailable) == (1, 0)


def test_a_read_only_store_runs_beside_the_writer_and_takes_no_writes(
    store: WorkStore, path: Path
) -> None:
    with WorkStore(path, read_only=True) as reader:
        assert operator.status(reader)["paused"] is False
        with pytest.raises(sqlite3.OperationalError):
            reader.set_paused(True)


def test_the_cli_shows_the_status_as_json(
    store: WorkStore, path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ticket(store, "t-working")
    store.close()
    assert main(["work", "status", "--store", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["open_tickets"] == 1


def test_the_cli_says_when_there_is_no_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["work", "status", "--store", str(tmp_path / "missing.sqlite")]) == 1
    assert "no work store" in capsys.readouterr().out


def test_the_cli_refuses_a_change_while_another_writer_holds_the_store(
    store: WorkStore, path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["work", "pause", "--store", str(path)]) == 1
    assert "StoreInUse" in capsys.readouterr().out
    assert store.paused is False


def test_the_cli_pauses_and_resumes_the_store(
    store: WorkStore, path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store.close()
    assert main(["work", "pause", "--store", str(path)]) == 0
    capsys.readouterr()
    assert main(["work", "status", "--store", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["paused"] is True
    assert main(["work", "resume", "--store", str(path)]) == 0


def test_the_cli_reports_an_unknown_ticket_on_stop(
    store: WorkStore, path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store.close()
    assert main(["work", "stop", "nope", "--store", str(path)]) == 1
    assert "no open ticket nope" in capsys.readouterr().out
