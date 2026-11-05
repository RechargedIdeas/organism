"""v1.12 Eval, one Trigger at a time: the rule assessment and the decision, with no store."""

from __future__ import annotations

from organism_sdk.work.assess import RuleAssessor
from organism_sdk.work.decide import EvalReason, decide, rule_reason
from organism_sdk.work.domain import Addressed, Outcome, Trigger, decision_key
from organism_sdk.work.gate import Reason, ScopeFacts, admit
from organism_sdk.work.policy import AcceptMode, AdmissionRow, Policy, Rule, SourcePolicy

OBSERVED = ScopeFacts(listened=True, observed=True, row="repo")
CI = Rule(id="ci-fix", instruction="fix failing CI", pattern=r"\bCI\b")


def policy(mode: AcceptMode, *rules: Rule) -> Policy:
    part = SourcePolicy(
        source="github", allowed=frozenset({"Alice"}), rows={"repo": AdmissionRow()}
    )
    return Policy(mode=mode, rules=rules, sources=(part,))


def trigger(text: str, *, actor: str = "alice", addressed: Addressed = Addressed.NONE) -> Trigger:
    return Trigger(
        id="m1",
        source="github",
        thread="github:issue-1",
        actor=actor,
        human=True,
        addressed=addressed,
        at="2026-11-04T00:00:00Z",
        text=text,
    )


def test_a_pattern_matches_case_insensitively_and_only_enabled_rules() -> None:
    rules = (
        Rule(id="ci-fix", instruction="fix CI", pattern="failing ci"),
        Rule(id="docs", instruction="fix docs", pattern="docs", enabled=False),
        Rule(id="chat", instruction="answer chat"),  # no pattern: never matched here
    )
    assessor = RuleAssessor(rules)
    text = "The FAILING CI job broke, and the docs too"
    assert assessor.assess(trigger(text)).matched == ("ci-fix",)
    assert assessor.assess(trigger("hello")).matched == ()


def test_matched_rules_come_back_sorted() -> None:
    rules = (
        Rule(id="b", instruction="x", pattern="go"),
        Rule(id="a", instruction="x", pattern="go"),
    )
    assert RuleAssessor(rules).assess(trigger("go")).matched == ("a", "b")


def test_a_refused_trigger_is_ignored_with_the_gates_reason() -> None:
    pol = policy(AcceptMode.AUTO, CI)
    stranger = trigger("fix CI", actor="mallory")
    admission = admit(stranger, ScopeFacts(listened=False), pol)
    decision = decide(stranger, admission, pol)
    assert decision.outcome is Outcome.IGNORE
    assert decision.reasons == (Reason.NOT_LISTENED.value,)


def test_an_explicit_request_is_accepted_without_an_assessment() -> None:
    pol = policy(AcceptMode.OFF, CI)
    asked = trigger("please look", addressed=Addressed.MENTION)
    decision = decide(asked, admit(asked, OBSERVED, pol), pol)
    assert decision.outcome is Outcome.ACCEPT
    assert decision.reasons == (Reason.ADDRESSED_BY_LISTED.value,)


def test_an_inferred_candidate_matching_a_graduated_rule_is_accepted_in_auto() -> None:
    graduated = Rule(id="ci-fix", instruction="fix CI", pattern=r"\bCI\b", auto=True)
    pol = policy(AcceptMode.AUTO, graduated)
    note = trigger("CI is red again")
    assessment = RuleAssessor(pol.rules).assess(note)
    decision = decide(note, admit(note, OBSERVED, pol), pol, assessment)
    assert decision.outcome is Outcome.ACCEPT
    assert decision.reasons == (Reason.CELL_INFERRED.value, rule_reason("ci-fix"))


def test_an_ungraduated_rule_is_only_a_would_accept_even_in_auto() -> None:
    pol = policy(AcceptMode.AUTO, CI)
    note = trigger("CI is red again")
    assessment = RuleAssessor(pol.rules).assess(note)
    decision = decide(note, admit(note, OBSERVED, pol), pol, assessment)
    assert decision.outcome is Outcome.IGNORE
    assert decision.reasons == (
        Reason.CELL_INFERRED.value,
        EvalReason.WOULD_ACCEPT.value,
        rule_reason("ci-fix"),
    )


def test_a_candidate_matching_no_rule_is_ignored() -> None:
    pol = policy(AcceptMode.AUTO, CI)
    note = trigger("lunch?")
    assessment = RuleAssessor(pol.rules).assess(note)
    decision = decide(note, admit(note, OBSERVED, pol), pol, assessment)
    assert decision.outcome is Outcome.IGNORE
    assert decision.reasons == (Reason.CELL_INFERRED.value, EvalReason.NO_RULE_MATCHED.value)


def test_an_inferred_candidate_is_refused_when_the_mode_is_off() -> None:
    pol = policy(AcceptMode.OFF, CI)
    note = trigger("CI is red")
    assessment = RuleAssessor(pol.rules).assess(note)
    decision = decide(note, admit(note, OBSERVED, pol), pol, assessment)
    assert decision.outcome is Outcome.IGNORE
    assert decision.reasons == (Reason.MODE_OFF.value,)


def test_a_failed_assessment_is_unavailable_and_says_why() -> None:
    pol = policy(AcceptMode.AUTO, CI)
    note = trigger("CI is red")
    decision = decide(note, admit(note, OBSERVED, pol), pol, assessment=None)
    assert decision.outcome is Outcome.UNAVAILABLE
    assert decision.reasons[-1] == EvalReason.ASSESSOR_UNAVAILABLE.value


def test_a_late_explicit_request_is_ignored_not_accepted() -> None:
    pol = policy(AcceptMode.AUTO, CI)
    asked = trigger("please look", addressed=Addressed.MENTION)
    decision = decide(asked, admit(asked, OBSERVED, pol), pol, late=True)
    assert decision.outcome is Outcome.IGNORE
    assert decision.reasons == (
        Reason.ADDRESSED_BY_LISTED.value,
        EvalReason.DEADLINE_PASSED.value,
    )


def test_a_late_candidate_is_ignored_even_when_the_assessor_failed() -> None:
    pol = policy(AcceptMode.AUTO, CI)
    note = trigger("CI is red")
    decision = decide(note, admit(note, OBSERVED, pol), pol, assessment=None, late=True)
    assert decision.outcome is Outcome.IGNORE
    assert decision.reasons[-1] == EvalReason.DEADLINE_PASSED.value


def test_the_decision_is_keyed_by_trigger_and_policy_version() -> None:
    pol = policy(AcceptMode.OFF)
    asked = trigger("please look", addressed=Addressed.MENTION)
    decision = decide(asked, admit(asked, OBSERVED, pol), pol)
    assert decision.id == decision_key("m1", pol.version)
    assert decision.trigger_id == "m1"
