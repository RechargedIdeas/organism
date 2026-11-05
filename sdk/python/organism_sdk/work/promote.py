"""Shadow promotion: when a rule may graduate from observe to auto (002). Design record: docs/v1.12/WORK_AGENT.md.

Pure. A rule graduates only on evidence: enough of its would-accept Decisions carry a person's
verdict, and most of those verdicts agree. The result is a new Policy with the graduated rules
marked, for the operator to adopt. Nothing here changes a stored Policy.

The checks follow the shape of generative PromoteGate. Its fields do not carry over directly:
a rule has no generated code, so the gate asks whether the rule is deterministic and stated.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

from organism_sdk.work.decide import EvalReason, rule_reason
from organism_sdk.work.domain import Decision, Outcome, Verdict, decision_key
from organism_sdk.work.policy import Policy, Rule

MIN_LABELED = 20  # would-accept Decisions with a verdict before a rule can graduate
MIN_SCORE = 0.9  # the share of those verdicts that must agree


@dataclass(frozen=True)
class ShadowGate:
    """The checks a rule must pass to graduate. ``ready()`` is True only when all hold."""

    rule_id: str
    deterministic: bool  # the rule has a pattern, so the assessor can judge it
    stated: bool  # the rule says what work it allows
    enabled: bool
    validated: bool  # enough would-accept Decisions carry a verdict
    score: float  # the share of those verdicts that agree
    min_score: float = MIN_SCORE
    graduated: bool = False

    def ready(self) -> bool:
        return (
            self.deterministic
            and self.stated
            and self.enabled
            and self.validated
            and self.score >= self.min_score
            and not self.graduated
        )


def shadow_gate(
    rule: Rule, decisions: Iterable[Decision], labels: Mapping[str, Verdict]
) -> ShadowGate:
    """The gate for one rule, from the Decisions to judge it by. Pass only current-version ones."""
    marker = rule_reason(rule.id)
    records = [
        decision
        for decision in decisions
        if decision.outcome is Outcome.IGNORE
        and EvalReason.WOULD_ACCEPT.value in decision.reasons
        and marker in decision.reasons
    ]
    verdicts = [labels[record.id] for record in records if record.id in labels]
    agreed = sum(1 for verdict in verdicts if verdict is Verdict.AGREE)
    return ShadowGate(
        rule_id=rule.id,
        deterministic=rule.pattern is not None,
        stated=bool(rule.instruction.strip()),
        enabled=rule.enabled,
        validated=len(verdicts) >= MIN_LABELED,
        score=agreed / len(verdicts) if verdicts else 0.0,
        graduated=rule.auto,
    )


def graduate(
    policy: Policy, decisions: Iterable[Decision], labels: Mapping[str, Verdict]
) -> Policy:
    """The Policy with each rule that passes its shadow gate marked auto.

    Only Decisions made under this Policy's own version count as evidence, so any change to the
    Policy starts the evidence again. The result is a new version for the operator to adopt.
    """
    current = [
        item for item in decisions if item.id == decision_key(item.trigger_id, policy.version)
    ]
    rules = tuple(
        replace(rule, auto=True) if shadow_gate(rule, current, labels).ready() else rule
        for rule in policy.rules
    )
    return replace(policy, rules=rules)
