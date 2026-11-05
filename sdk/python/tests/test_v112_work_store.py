"""v1.12 work store: intake, rounds, tickets, receipts, effects and pause, in one process."""

from __future__ import annotations

import dataclasses
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from organism_sdk.work import codec
from organism_sdk.work.domain import (
    Addressed,
    Assignment,
    AssignmentState,
    Decision,
    Mandate,
    Outcome,
    Report,
    Strength,
    Ticket,
    Trigger,
    Via,
)
from organism_sdk.work.store import (
    Receipt,
    ReceiptStatus,
    RunReport,
    StoreInUse,
    WorkStore,
    backoff_seconds,
)

MANDATE = Mandate(
    policy_version="sha256:test",
    strength=Strength.EXPLICIT,
    via=Via.ADDRESSED,
    source="github",
    row="repo",
    sender="alice",
    rules=("ci-fix",),
)


class Clock:
    """A clock the test moves by hand."""

    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def trigger(n: int, *, thread: str = "github:issue-1") -> Trigger:
    return Trigger(
        id=f"m{n}",
        source="github",
        thread=thread,
        actor="alice",
        human=True,
        addressed=Addressed.MENTION,
        at=f"2026-11-04T00:00:{n:02d}Z",
        text=f"message {n}",
    )


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(tmp_path: Path, clock: Clock) -> Iterator[WorkStore]:
    handle = WorkStore(tmp_path / "work.sqlite", clock=clock)
    yield handle
    handle.close()


def handle_into(seen: list[dict[str, Any]]) -> Callable[[Mapping[str, Any]], None]:
    def handle(payload: Mapping[str, Any]) -> None:
        seen.append(dict(payload))

    return handle


def boom(payload: Mapping[str, Any]) -> None:
    raise RuntimeError("provider down")


def ok(payload: Mapping[str, Any]) -> None:
    return None


# Intake


def test_a_trigger_is_stored_once(store: WorkStore) -> None:
    assert store.receive(trigger(1)) is True
    assert store.receive(trigger(1)) is False
    assert store.trigger_count() == 1


def test_a_stored_trigger_reads_back_equal(store: WorkStore) -> None:
    stored = trigger(1)
    store.receive(stored)
    assert store.trigger("m1") == stored
    assert store.trigger("missing") is None


def test_the_triggers_of_a_thread_come_in_time_order(store: WorkStore) -> None:
    for n in (3, 1, 2):
        store.receive(trigger(n))
    store.receive(trigger(4, thread="github:issue-2"))
    assert [item.id for item in store.triggers_in_thread("github:issue-1")] == ["m1", "m2", "m3"]


def test_a_round_commits_its_triggers_cursor_and_effects_together(store: WorkStore) -> None:
    new = store.commit_round(
        "github",
        [trigger(1), trigger(2)],
        cursor="c2",
        effects=[("reply", "m1", {"text": "on it"})],
    )
    assert new == 2
    assert store.cursor("github") == "c2"
    [effect] = store.pending_effects()
    assert (effect.kind, effect.key, dict(effect.payload)) == ("reply", "m1", {"text": "on it"})


def test_a_round_stores_a_repeated_trigger_once(store: WorkStore) -> None:
    assert store.commit_round("github", [trigger(1), trigger(1)], cursor="c1") == 1


def test_a_failed_round_stores_nothing(store: WorkStore) -> None:
    with pytest.raises(RuntimeError, match="before commit"), store.transaction():
        store.commit_round(
            "github",
            [trigger(1), trigger(2)],
            cursor="c2",
            effects=[("reply", "m1", {"text": "on it"})],
        )
        raise RuntimeError("before commit")
    assert store.trigger_count() == 0
    assert store.cursor("github") is None
    assert store.pending_effects() == []


def test_nested_transactions_join_the_outer_one(store: WorkStore) -> None:
    with pytest.raises(RuntimeError), store.transaction():
        store.receive(trigger(1))
        with store.transaction():
            store.receive(trigger(2))
        raise RuntimeError("abort the outer transaction")
    assert store.trigger_count() == 0


# Decisions, Tickets and Assignments


def test_a_decision_is_stored_once(store: WorkStore) -> None:
    decision = Decision(id="d1", trigger_id="m1", outcome=Outcome.ACCEPT, reasons=("explicit",))
    assert store.save_decision(decision) is True
    assert store.save_decision(decision) is False
    assert store.decisions_for("m1") == [decision]


def test_a_ticket_round_trips_and_ended_tickets_leave_the_open_list(store: WorkStore) -> None:
    running = Assignment(id="a1", ticket_id="t1", state=AssignmentState.RUNNING)
    ticket = Ticket(id="t1", mandate=MANDATE, assignment=running, latest_report=Report.PROGRESS)
    other = Ticket(id="t2", mandate=MANDATE)
    store.save_ticket(ticket)
    store.save_ticket(other)
    assert store.ticket("t1") == ticket
    assert store.open_tickets() == [ticket, other]

    ended = dataclasses.replace(ticket, ended=True, latest_report=Report.DROPPED)
    store.save_ticket(ended)
    assert store.ticket("t1") == ended
    assert store.open_tickets() == [other]


def test_the_assignments_of_a_ticket_keep_their_order(store: WorkStore) -> None:
    first = Assignment(id="a1", ticket_id="t1", state=AssignmentState.ENDED)
    second = Assignment(id="a2", ticket_id="t1", state=AssignmentState.PENDING)
    store.save_assignment(first)
    store.save_assignment(second)
    store.save_assignment(Assignment(id="a3", ticket_id="t2", state=AssignmentState.PENDING))
    store.save_assignment(dataclasses.replace(first, state=AssignmentState.RUNNING))
    assert store.assignments_of("t1") == [
        dataclasses.replace(first, state=AssignmentState.RUNNING),
        second,
    ]


# Outbound receipts


def test_a_receipt_is_queued_once_and_settled(store: WorkStore) -> None:
    assert store.add_receipt("r1", ticket_id="t1", conversation="issue-1", text="on it") is True
    assert store.add_receipt("r1", ticket_id="t1", conversation="issue-1", text="again") is False
    assert store.receipt("r1") == Receipt(
        id="r1",
        ticket_id="t1",
        conversation="issue-1",
        text="on it",
        status=ReceiptStatus.PENDING,
        reason=None,
    )

    store.settle_receipt("r1", ReceiptStatus.SENT)
    sent = store.receipt("r1")
    assert sent is not None
    assert sent.status is ReceiptStatus.SENT

    store.add_receipt("r2", ticket_id="t1", conversation="issue-1", text="done")
    store.settle_receipt("r2", ReceiptStatus.DROPPED, "conversation deleted")
    dropped = store.receipt("r2")
    assert dropped is not None
    assert (dropped.status, dropped.reason) == (ReceiptStatus.DROPPED, "conversation deleted")


def test_settling_an_unknown_receipt_raises(store: WorkStore) -> None:
    with pytest.raises(KeyError):
        store.settle_receipt("nope", ReceiptStatus.SENT)


# Effects


def test_an_effect_runs_once_and_leaves_the_queue(store: WorkStore) -> None:
    store.enqueue("reply", "m1", {"text": "hi"})
    seen: list[dict[str, Any]] = []
    assert store.run_due({"reply": handle_into(seen)}) == RunReport(completed=1, failed=0)
    assert seen == [{"text": "hi"}]
    assert store.pending_effects() == []
    assert store.run_due({"reply": handle_into(seen)}) == RunReport(completed=0, failed=0)


def test_a_failing_effect_waits_out_its_backoff(store: WorkStore, clock: Clock) -> None:
    store.enqueue("reply", "m1", {"text": "hi"})
    assert store.run_due({"reply": boom}) == RunReport(completed=0, failed=1)
    [effect] = store.pending_effects()
    assert effect.attempts == 1
    assert effect.due_at == pytest.approx(1_005.0)
    assert effect.last_error == "RuntimeError: provider down"

    assert store.run_due({"reply": boom}) == RunReport(completed=0, failed=0)
    clock.now += 4
    assert store.run_due({"reply": boom}) == RunReport(completed=0, failed=0)
    clock.now += 1
    assert store.run_due({"reply": boom}) == RunReport(completed=0, failed=1)
    [effect] = store.pending_effects()
    assert effect.attempts == 2
    assert effect.due_at == pytest.approx(1_015.0)


def test_the_backoff_doubles_from_five_seconds_up_to_five_minutes() -> None:
    assert [backoff_seconds(n) for n in range(1, 9)] == [5, 10, 20, 40, 80, 160, 300, 300]
    with pytest.raises(ValueError):
        backoff_seconds(0)


def test_enqueue_replaces_a_waiting_payload_and_keeps_its_place(
    store: WorkStore, clock: Clock
) -> None:
    store.enqueue("reply", "m1", {"text": "first"})
    store.enqueue("reply", "m2", {"text": "second"})
    store.run_due({"reply": boom})  # both fail and wait five seconds
    clock.now += 1
    store.enqueue("reply", "m1", {"text": "first, edited"})  # m1 is due at once, m2 still waits
    edited, waiting = store.pending_effects()
    assert (edited.key, waiting.key) == ("m1", "m2")
    assert dict(edited.payload) == {"text": "first, edited"}
    assert edited.due_at == clock.now
    assert edited.attempts == 1
    assert waiting.due_at == pytest.approx(1_005.0)
    seen: list[dict[str, Any]] = []
    assert store.run_due({"reply": handle_into(seen)}) == RunReport(completed=1, failed=0)
    assert seen == [{"text": "first, edited"}]


def test_a_paused_store_records_but_runs_nothing(store: WorkStore) -> None:
    store.set_paused(True)
    assert store.paused is True
    assert store.receive(trigger(1)) is True
    store.enqueue("reply", "m1", {"text": "hi"})
    seen: list[dict[str, Any]] = []
    assert store.run_due({"reply": handle_into(seen)}) == RunReport(completed=0, failed=0)
    assert seen == []
    assert len(store.pending_effects()) == 1

    store.set_paused(False)
    assert store.run_due({"reply": handle_into(seen)}) == RunReport(completed=1, failed=0)


def test_an_effect_of_a_kind_without_a_handler_is_left_alone(store: WorkStore) -> None:
    store.enqueue("other", "x", {})
    assert store.run_due({"reply": ok}) == RunReport(completed=0, failed=0)
    [effect] = store.pending_effects()
    assert effect.attempts == 0


def test_a_run_stops_at_its_limit(store: WorkStore) -> None:
    for key in ("a", "b", "c"):
        store.enqueue("reply", key, {})
    assert store.run_due({"reply": ok}, limit=2) == RunReport(completed=2, failed=0)
    assert [effect.key for effect in store.pending_effects()] == ["c"]


def test_a_payload_queued_during_its_run_is_not_lost(store: WorkStore) -> None:
    store.enqueue("reply", "m1", {"text": "first"})
    seen: list[dict[str, Any]] = []

    def handler(payload: Mapping[str, Any]) -> None:
        seen.append(dict(payload))
        if payload["text"] == "first":
            store.enqueue("reply", "m1", {"text": "second"})

    store.run_due({"reply": handler})
    [pending] = store.pending_effects()
    assert dict(pending.payload) == {"text": "second"}
    store.run_due({"reply": handler})
    assert seen == [{"text": "first"}, {"text": "second"}]
    assert store.pending_effects() == []


# Persistence and schema


def test_a_second_writer_is_refused_until_the_first_closes(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    with WorkStore(path), pytest.raises(StoreInUse):
        WorkStore(path)
    WorkStore(path).close()


def test_closing_twice_does_nothing(tmp_path: Path) -> None:
    store = WorkStore(tmp_path / "work.sqlite")
    store.close()
    store.close()


def test_the_store_reopens_with_its_state(tmp_path: Path, clock: Clock) -> None:
    path = tmp_path / "work.sqlite"
    first = WorkStore(path, clock=clock)
    first.receive(trigger(1))
    first.set_paused(True)
    first.close()
    second = WorkStore(path, clock=clock)
    assert second.trigger("m1") == trigger(1)
    assert second.paused is True
    second.close()


def test_a_store_of_another_schema_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    WorkStore(path).close()
    connection = sqlite3.connect(str(path))
    connection.execute("UPDATE flags SET value = '0' WHERE name = 'schema'")
    connection.commit()
    connection.close()
    with pytest.raises(RuntimeError, match="schema 0"):
        WorkStore(path)


# Encoding


def test_every_domain_type_round_trips_through_the_codec() -> None:
    values: list[tuple[Any, Any]] = [
        (Trigger, trigger(1)),
        (Mandate, MANDATE),
        (Assignment, Assignment(id="a1", ticket_id="t1", state=AssignmentState.RUNNING)),
        (
            Ticket,
            Ticket(
                id="t1",
                mandate=MANDATE,
                ended=True,
                assignment=Assignment(id="a1", ticket_id="t1", state=AssignmentState.ENDED),
                latest_report=Report.BLOCKED,
                attention=True,
                delivery_failed=True,
                person_message_after_report=True,
            ),
        ),
        (Decision, Decision(id="d1", trigger_id="m1", outcome=Outcome.STOP, reasons=("x", "y"))),
    ]
    for hint, value in values:
        assert codec.from_text(hint, codec.to_text(value)) == value


def test_the_codec_writes_enums_by_value_and_sorts_sets() -> None:
    text = codec.to_text(MANDATE)
    assert '"strength":"explicit"' in text
    assert '"via":"addressed"' in text
    assert codec.to_text(frozenset({"b", "a"})) == '["a","b"]'


def test_none_decodes_to_none() -> None:
    assert codec.decode(str | None, None) is None
