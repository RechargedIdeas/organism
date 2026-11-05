"""v1.12 work stages: the table of the execution document, row by row, first match wins."""

from __future__ import annotations

import pytest
from organism_sdk.work.domain import (
    Assignment,
    AssignmentState,
    Mandate,
    Report,
    Strength,
    Ticket,
    Via,
)
from organism_sdk.work.stage import Stage, stage_of, waits_for_person

MANDATE = Mandate(
    policy_version="sha256:test",
    strength=Strength.EXPLICIT,
    via=Via.ADDRESSED,
    source="github",
    row="repo",
    sender="alice",
)
RUNNING = AssignmentState.RUNNING
PENDING = AssignmentState.PENDING
ENDED = AssignmentState.ENDED


def ticket(
    *,
    state: AssignmentState | None = None,
    report: Report | None = None,
    attention: bool = False,
    delivery_failed: bool = False,
    person_message_after_report: bool = False,
    ended: bool = False,
) -> Ticket:
    assignment = None if state is None else Assignment(id="a1", ticket_id="t1", state=state)
    return Ticket(
        id="t1",
        mandate=MANDATE,
        assignment=assignment,
        latest_report=report,
        attention=attention,
        delivery_failed=delivery_failed,
        person_message_after_report=person_message_after_report,
        ended=ended,
    )


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        # Row 1: an Input the Executor never received.
        (ticket(delivery_failed=True), Stage.PERSON_DELIVERY),
        # Row 2: a question for a person. It beats a blocked report beneath it.
        (ticket(attention=True, state=ENDED, report=Report.BLOCKED), Stage.PERSON_ANSWER),
        # Row 3: a ready report awaits review, even with a run still going.
        (ticket(state=RUNNING, report=Report.READY), Stage.PERSON_REVIEW),
        # Row 4: blocked or failed with nobody having written since.
        (ticket(state=ENDED, report=Report.BLOCKED), Stage.PERSON_BLOCKED),
        (ticket(state=ENDED, report=Report.FAILED), Stage.PERSON_BLOCKED),
        (ticket(state=PENDING, report=Report.FAILED), Stage.PERSON_BLOCKED),
        # Once a person writes, row 4 no longer holds and the work goes on.
        (
            ticket(state=RUNNING, report=Report.BLOCKED, person_message_after_report=True),
            Stage.WORKING,
        ),
        # Row 5: no Assignment, or a pending one.
        (ticket(), Stage.QUEUED),
        (ticket(state=PENDING), Stage.QUEUED),
        (
            ticket(report=Report.BLOCKED, person_message_after_report=True),
            Stage.QUEUED,
        ),
        # Row 6: waiting for a Trigger.
        (ticket(state=RUNNING, report=Report.WAITING), Stage.IDLE),
        (ticket(state=ENDED, report=Report.PROGRESS), Stage.IDLE),
        (ticket(state=ENDED), Stage.IDLE),
        # Row 7: everything else.
        (ticket(state=RUNNING, report=Report.PROGRESS), Stage.WORKING),
        (ticket(state=RUNNING), Stage.WORKING),
    ],
)
def test_stage_follows_the_table(subject: Ticket, expected: Stage) -> None:
    assert stage_of(subject) == expected


def test_an_ended_ticket_has_no_stage() -> None:
    with pytest.raises(ValueError, match="has ended"):
        stage_of(ticket(ended=True, state=ENDED))


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        (ticket(report=Report.BLOCKED), True),
        (ticket(report=Report.FAILED), True),
        (ticket(report=Report.BLOCKED, person_message_after_report=True), False),
        (ticket(report=Report.WAITING), False),
        (ticket(report=Report.READY), False),
        (ticket(), False),
    ],
)
def test_waits_for_person_only_while_blocked_or_failed_and_unanswered(
    subject: Ticket, expected: bool
) -> None:
    assert waits_for_person(subject) is expected
