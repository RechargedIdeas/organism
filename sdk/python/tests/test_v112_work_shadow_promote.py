"""v1.12 shadow promotion: a rule graduates only on enough agreeing evidence from its own version."""

from __future__ import annotations

from organism_sdk.work.decide import EvalReason, rule_reason
from organism_sdk.work.domain import Decision, Outcome, Verdict, decision_key
from organism_sdk.work.policy import AcceptMode, Policy, Rule
from organism_sdk.work.promote import MIN_LABELED, graduate, shadow_gate

CI = Rule(id="ci-fix", instruction="fix CI", pattern="CI")


def policy(*rules: Rule) -> Policy:
    return Policy(mode=AcceptMode.OBSERVE, rules=rules)


def would_accept(pol: Policy, n: int, rule: str = "ci-fix") -> Decision:
    trigger_id = f"m{n}"
    reasons = ("cell_inferred", EvalReason.WOULD_ACCEPT.value, rule_reason(rule))
    return Decision(
        id=decision_key(trigger_id, pol.version),
        trigger_id=trigger_id,
        outcome=Outcome.IGNORE,
        reasons=reasons,
    )


def judged(pol: Policy, verdicts: list[Verdict]) -> tuple[list[Decision], dict[str, Verdict]]:
    decisions = [would_accept(pol, n) for n in range(len(verdicts))]
    return decisions, {d.id: v for d, v in zip(decisions, verdicts, strict=True)}


def test_a_rule_needs_enough_verdicts_before_it_can_graduate() -> None:
    pol = policy(CI)
    decisions, labels = judged(pol, [Verdict.AGREE] * (MIN_LABELED - 1))
    gate = shadow_gate(CI, decisions, labels)
    assert gate.validated is False
    assert gate.ready() is False


def test_enough_agreeing_verdicts_make_a_rule_ready() -> None:
    pol = policy(CI)
    decisions, labels = judged(pol, [Verdict.AGREE] * MIN_LABELED)
    assert shadow_gate(CI, decisions, labels).ready() is True


def test_the_score_must_reach_the_minimum() -> None:
    pol = policy(CI)
    # 18 agreeing of 20 is exactly 0.9, which passes. 17 of 20 is 0.85, which does not.
    passing = [Verdict.AGREE] * 18 + [Verdict.DISAGREE] * 2
    failing = [Verdict.AGREE] * 17 + [Verdict.DISAGREE] * 3
    assert shadow_gate(CI, *judged(pol, passing)).ready() is True
    assert shadow_gate(CI, *judged(pol, failing)).ready() is False


def test_only_would_accepts_of_this_rule_count() -> None:
    pol = policy(CI)
    decisions, labels = judged(pol, [Verdict.AGREE] * MIN_LABELED)
    other = [would_accept(pol, 100 + n, rule="docs") for n in range(MIN_LABELED)]
    labels.update({decision.id: Verdict.DISAGREE for decision in other})
    assert shadow_gate(CI, decisions + other, labels).ready() is True


def test_an_unlabeled_would_accept_is_not_evidence() -> None:
    pol = policy(CI)
    decisions, _ = judged(pol, [Verdict.AGREE] * MIN_LABELED)
    assert shadow_gate(CI, decisions, {}).validated is False


def test_a_decision_under_an_older_version_is_not_evidence() -> None:
    old = policy(CI)
    changed = Policy(
        mode=AcceptMode.OBSERVE,
        rules=(Rule(id="ci-fix", instruction="fix CI now", pattern="CI"),),
    )
    decisions, labels = judged(old, [Verdict.AGREE] * MIN_LABELED)
    assert graduate(changed, decisions, labels).rules[0].auto is False


def test_graduate_marks_only_the_ready_rules_and_makes_a_new_version() -> None:
    docs = Rule(id="docs", instruction="fix docs", pattern="docs")
    pol = policy(CI, docs)
    decisions, labels = judged(pol, [Verdict.AGREE] * MIN_LABELED)
    graduated = graduate(pol, decisions, labels)
    flags = {rule.id: rule.auto for rule in graduated.rules}
    assert flags == {"ci-fix": True, "docs": False}
    assert graduated.version != pol.version


def test_a_rule_without_a_pattern_never_graduates() -> None:
    chat = Rule(id="chat", instruction="answer chat")
    pol = policy(chat)
    decisions = [would_accept(pol, n, rule="chat") for n in range(MIN_LABELED)]
    labels = {decision.id: Verdict.AGREE for decision in decisions}
    assert shadow_gate(chat, decisions, labels).ready() is False
    assert graduate(pol, decisions, labels).rules[0].auto is False


def test_a_graduated_rule_is_not_ready_again() -> None:
    pol = policy(Rule(id="ci-fix", instruction="fix CI", pattern="CI", auto=True))
    decisions, labels = judged(pol, [Verdict.AGREE] * MIN_LABELED)
    assert shadow_gate(pol.rules[0], decisions, labels).ready() is False
