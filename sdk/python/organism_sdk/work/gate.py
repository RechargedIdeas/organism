"""The gate: the deterministic first layer of Eval (002). Design record: docs/v1.12/WORK_AGENT.md.

Pure. A Trigger, its receiving scope and a Policy give a strength and its basis. No model
is consulted. Judging proactive candidates is a later layer (W4).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from organism_sdk.work.domain import Addressed, Strength, Trigger, Via
from organism_sdk.work.policy import AcceptMode, AdmissionRow, Cell, Policy, SourcePolicy


@dataclass(frozen=True)
class ScopeFacts:
    """What a Source reports about the scope a Trigger arrived in (002).

    ``listened``: the Source reads this scope. ``observed``: it receives unaddressed messages
    there, so the unaddressed cells apply. ``row``: the admission row the scope belongs to.
    """

    listened: bool
    observed: bool = False
    row: str | None = None


class Reason(str, Enum):
    """Why the gate decided what it did. Codes, so the panel can word each one."""

    NOT_LISTENED = "not_listened"
    UNKNOWN_SOURCE = "unknown_source"
    NOT_A_LISTED_BOT = "not_a_listed_bot"
    NOT_OBSERVED = "not_observed"
    NO_ROW = "no_row"
    ADDRESSED_BY_LISTED = "addressed_by_listed"
    FOLLOWUP_LISTED = "followup_listed"
    FOLLOWUP_UNLISTED = "followup_unlisted"
    CELL_EXPLICIT = "cell_explicit"
    CELL_INFERRED = "cell_inferred"
    CELL_IGNORED = "cell_ignored"
    BOT_LISTED = "bot_listed"
    MODE_OFF = "mode_off"


@dataclass(frozen=True)
class Admission:
    """The gate's answer. ``via`` is None when the Trigger is not admitted."""

    strength: Strength
    reason: Reason
    via: Via | None = None


def admit(
    trigger: Trigger, scope: ScopeFacts, policy: Policy, *, has_tickets: bool = False
) -> Admission:
    """Decide how strongly a Trigger may start work.

    ``has_tickets`` is True when the Trigger's Thread already has a Ticket, so a message
    from a person there is a follow-up.
    """
    if not scope.listened:
        return _refused(Reason.NOT_LISTENED)
    source = policy.source(trigger.source)
    if source is None:
        return _refused(Reason.UNKNOWN_SOURCE)
    row = source.rows.get(scope.row) if scope.row is not None else None
    addressed = trigger.addressed is not Addressed.NONE
    if trigger.actor is None:
        # An event with no sender, such as a CI result, has only the last cell.
        return _from_cells(policy.mode, row, scope, listed=False, addressed=addressed)
    if not trigger.human:
        return _from_bot(trigger.actor, addressed, scope, source, policy.mode)
    listed = trigger.actor.casefold() in source.allowed
    if listed and addressed:
        return Admission(Strength.EXPLICIT, Reason.ADDRESSED_BY_LISTED, Via.ADDRESSED)
    if has_tickets:
        return _followup(policy.mode, row, listed=listed, addressed=addressed)
    return _from_cells(policy.mode, row, scope, listed=listed, addressed=addressed)


def _followup(
    mode: AcceptMode, row: AdmissionRow | None, *, listed: bool, addressed: bool
) -> Admission:
    if listed:
        return Admission(Strength.EXPLICIT, Reason.FOLLOWUP_LISTED, Via.FOLLOWUP)
    if addressed and row is not None and row.unlisted_addressed is Cell.EXPLICIT:
        return Admission(Strength.EXPLICIT, Reason.CELL_EXPLICIT, Via.ADMISSION)
    return _inferred(mode, Reason.FOLLOWUP_UNLISTED, Via.FOLLOWUP)


def _from_cells(
    mode: AcceptMode,
    row: AdmissionRow | None,
    scope: ScopeFacts,
    *,
    listed: bool,
    addressed: bool,
) -> Admission:
    if not addressed and not scope.observed:
        return _refused(Reason.NOT_OBSERVED)
    if row is None:
        return _refused(Reason.NO_ROW)
    cell = _cell_for(row, listed=listed, addressed=addressed)
    if cell is Cell.EXPLICIT:
        return Admission(Strength.EXPLICIT, Reason.CELL_EXPLICIT, Via.ADMISSION)
    if cell is Cell.INFERRED:
        return _inferred(mode, Reason.CELL_INFERRED, Via.ADMISSION)
    return _refused(Reason.CELL_IGNORED)


def _cell_for(row: AdmissionRow, *, listed: bool, addressed: bool) -> Cell:
    # A listed person who addresses the agent is explicit before any cell is read, so an
    # addressed message reaching this point comes from an unlisted sender.
    if addressed:
        return row.unlisted_addressed
    if listed:
        return row.listed_unaddressed
    return row.unlisted_unaddressed


def _from_bot(
    actor: str,
    addressed: bool,
    scope: ScopeFacts,
    source: SourcePolicy,
    mode: AcceptMode,
) -> Admission:
    if actor.casefold() not in source.bots:
        return _refused(Reason.NOT_A_LISTED_BOT)
    if not addressed and not scope.observed:
        return _refused(Reason.NOT_OBSERVED)
    return _inferred(mode, Reason.BOT_LISTED, Via.BOT)


def _inferred(mode: AcceptMode, reason: Reason, via: Via) -> Admission:
    if mode is AcceptMode.OFF:
        return _refused(Reason.MODE_OFF)
    return Admission(Strength.INFERRED, reason, via)


def _refused(reason: Reason) -> Admission:
    return Admission(Strength.NOT_ADMITTED, reason)
