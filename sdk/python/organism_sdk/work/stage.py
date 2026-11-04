"""Ticket stages (003). Design record: docs/v1.12/WORK_AGENT.md.

The table is read from top to bottom and the first matching row wins. Each stage names
what the Ticket waits for, so a person can see at a glance whether the work is theirs.
"""

from __future__ import annotations

from enum import Enum

from organism_sdk.work.domain import AssignmentState, Report, Ticket


class Stage(str, Enum):
    """The stage of an open Ticket. The values follow the superagent's stage names."""

    PERSON_DELIVERY = "person/delivery"
    PERSON_ANSWER = "person/answer"
    PERSON_REVIEW = "person/review"
    PERSON_BLOCKED = "person/blocked"
    QUEUED = "working/queued"
    IDLE = "idle"
    WORKING = "working"


def waits_for_person(ticket: Ticket) -> bool:
    """True while the latest report is blocked or failed and no person has written since.

    Automatic Inputs and failed launches are held while this holds.
    """
    return ticket.latest_report in (Report.BLOCKED, Report.FAILED) and not (
        ticket.person_message_after_report
    )


def stage_of(ticket: Ticket) -> Stage:
    """The stage of an open Ticket. An ended Ticket has none."""
    if ticket.ended:
        raise ValueError(f"ticket {ticket.id} has ended and has no stage")
    if ticket.delivery_failed:
        return Stage.PERSON_DELIVERY
    if ticket.attention:
        return Stage.PERSON_ANSWER
    if ticket.latest_report is Report.READY:
        return Stage.PERSON_REVIEW
    if waits_for_person(ticket):
        return Stage.PERSON_BLOCKED
    assignment = ticket.assignment
    if assignment is None or assignment.state is AssignmentState.PENDING:
        return Stage.QUEUED
    if ticket.latest_report is Report.WAITING or assignment.state is AssignmentState.ENDED:
        return Stage.IDLE
    return Stage.WORKING
