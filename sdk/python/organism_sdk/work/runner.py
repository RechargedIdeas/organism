"""Eval over the store: decide every undecided Trigger under one Policy version (002).

Design record: docs/v1.12/WORK_AGENT.md. The store supplies the Triggers and keeps the Decisions,
and the assessor judges them. The decisions themselves come from decide.py, so the rules stay
testable without a store. A Trigger that already has a Decision under this Policy version is
skipped, so a run repeated after a crash never decides a Trigger twice.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from organism_sdk.work.assess import Assessment, RuleAssessor
from organism_sdk.work.decide import decide
from organism_sdk.work.domain import Outcome, Strength, Trigger
from organism_sdk.work.gate import ScopeFacts, admit
from organism_sdk.work.policy import Policy
from organism_sdk.work.store import WorkStore

DEADLINE_S = 3600.0  # a Trigger older than this when Eval reaches it is ignored, not acted on


@dataclass(frozen=True)
class EvalReport:
    """What one run did: the Decisions it saved, and the Triggers left for the next run."""

    decided: int
    unavailable: int


def evaluate(
    store: WorkStore,
    policy: Policy,
    assessor: RuleAssessor,
    scope_of: Callable[[Trigger], ScopeFacts],
    *,
    deadline_s: float = DEADLINE_S,
) -> EvalReport:
    """Decide every undecided Trigger. An unavailable one is left for the next run."""
    now = store.now()
    decided = 0
    unavailable = 0
    for trigger, received in store.undecided(policy.version):
        ticket = store.ticket_for_thread(trigger.thread)
        scope = scope_of(trigger)
        admission = admit(trigger, scope, policy, has_tickets=ticket is not None)
        late = now - received > deadline_s
        assessment = None
        if admission.strength is Strength.INFERRED and not late:
            assessment = _assess(assessor, trigger)
        decision = decide(trigger, admission, policy, assessment, late=late, row=scope.row)
        if decision.outcome is Outcome.UNAVAILABLE:
            unavailable += 1
            continue
        store.save_decision(decision)
        decided += 1
    return EvalReport(decided=decided, unavailable=unavailable)


def _assess(assessor: RuleAssessor, trigger: Trigger) -> Assessment | None:
    try:
        return assessor.assess(trigger)
    except Exception:  # noqa: BLE001 - a failed assessment leaves the Trigger for the next run
        return None
