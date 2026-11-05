"""Eval for one Trigger: its outcome under one Policy version (002). Design record: docs/v1.12/WORK_AGENT.md.

Pure. The gate's admission and the rule assessment give the outcome, and the reasons are codes
so the panel can word them. A candidate is accepted only when the Policy's mode and a graduated
rule allow it. Otherwise a candidate that matched a rule is recorded as a would-accept, which is
the evidence that shadow promotion (promote.py) judges the rule by.
"""

from __future__ import annotations

from enum import Enum

from organism_sdk.work.assess import Assessment
from organism_sdk.work.domain import Decision, Outcome, Strength, Trigger, decision_key
from organism_sdk.work.gate import Admission
from organism_sdk.work.policy import Policy, may_accept_inferred


class EvalReason(str, Enum):
    """Why Eval decided what it did, beyond the gate's own reason."""

    WOULD_ACCEPT = "would_accept"
    NO_RULE_MATCHED = "no_rule_matched"
    DEADLINE_PASSED = "deadline_passed"
    ASSESSOR_UNAVAILABLE = "assessor_unavailable"


def rule_reason(rule_id: str) -> str:
    """The reason code that names a rule a Trigger matched."""
    return f"rule:{rule_id}"


def decide(
    trigger: Trigger,
    admission: Admission,
    policy: Policy,
    assessment: Assessment | None = None,
    *,
    late: bool = False,
) -> Decision:
    """The Decision for one Trigger under one Policy version.

    ``assessment`` is None when the assessor was not asked or failed. ``late`` is True when the
    Trigger has waited past its deadline. A late Trigger is ignored, even an explicit one: a
    Policy change re-evaluates the backlog, and this stops old requests from starting work.
    The first reason is always the gate's own.
    """
    key = decision_key(trigger.id, policy.version)
    first = admission.reason.value
    if admission.strength is Strength.NOT_ADMITTED:
        return _decision(key, trigger, Outcome.IGNORE, (first,))
    if late:
        return _decision(key, trigger, Outcome.IGNORE, (first, EvalReason.DEADLINE_PASSED.value))
    if admission.strength is Strength.EXPLICIT:
        return _decision(key, trigger, Outcome.ACCEPT, (first,))
    if assessment is None:
        unavailable = (first, EvalReason.ASSESSOR_UNAVAILABLE.value)
        return _decision(key, trigger, Outcome.UNAVAILABLE, unavailable)
    matched = tuple(rule_reason(rule_id) for rule_id in assessment.matched)
    if may_accept_inferred(policy, assessment.matched):
        return _decision(key, trigger, Outcome.ACCEPT, (first, *matched))
    if assessment.matched:
        would = (first, EvalReason.WOULD_ACCEPT.value, *matched)
        return _decision(key, trigger, Outcome.IGNORE, would)
    return _decision(key, trigger, Outcome.IGNORE, (first, EvalReason.NO_RULE_MATCHED.value))


def _decision(key: str, trigger: Trigger, outcome: Outcome, reasons: tuple[str, ...]) -> Decision:
    return Decision(id=key, trigger_id=trigger.id, outcome=outcome, reasons=reasons)
