"""v1.11 MoA capability routing: scorer decisions and the Phase 2 shadow gate."""

from __future__ import annotations

from pathlib import Path

import pytest
from organism_sdk.contract import ModuleRole
from organism_sdk.moa import shadow
from organism_sdk.moa.experts import BaseExpert, CapabilityDescriptor, ExpertOutput
from organism_sdk.moa.reference import reference_experts
from organism_sdk.moa.scorer import ROUTE_EXPERT, ROUTE_LLM_FALLBACK, ROUTE_UNSURE, LexicalScorer

DATA = Path(__file__).parent / "data" / "moa_routing_synthetic.json"


class _ConstantExpert(BaseExpert):
    """Expert on the pattern_recognition form with a keyword no query uses."""

    def __init__(self) -> None:
        super().__init__(
            CapabilityDescriptor(
                expert_id="constant",
                domain="constant",
                task_forms=("pattern_recognition",),
                keywords=("zzzunused",),
                role=ModuleRole.PREDICTION,
            )
        )

    def answer(self, query: str, form: str | None = None) -> ExpertOutput:
        return ExpertOutput("constant", "{}", 0.5, schema_valid=True)


def test_clear_leader_routes_to_expert():
    decision = LexicalScorer().decide("Extract the dates and numbers", reference_experts())
    assert decision.route == ROUTE_EXPERT
    assert decision.expert_id == "extractor"
    assert decision.reason == "clear_leader"


def test_no_keyword_evidence_is_unsure_by_default():
    decision = LexicalScorer().decide("Good morning", reference_experts())
    assert decision.route == ROUTE_UNSURE
    assert decision.expert_id is None
    assert decision.reason == "no_expert_clears_min_score"


def test_no_keyword_evidence_routes_to_llm_fallback_only_when_enabled():
    scorer = LexicalScorer(allow_llm_fallback=True)
    decision = scorer.decide("Good morning", reference_experts())
    assert decision.route == ROUTE_LLM_FALLBACK


def test_ambiguous_top_two_is_unsure():
    # "extract" hits the extractor and "remind" hits the intent classifier, one each.
    decision = LexicalScorer().decide("Extract and remind me", reference_experts())
    assert decision.route == ROUTE_UNSURE
    assert decision.reason == "ambiguous_top_two"


def test_no_candidates_is_unsure():
    decision = LexicalScorer().decide("anything", [])
    assert decision.route == ROUTE_UNSURE
    assert decision.reason == "no_candidates"


def test_scoring_saturates_so_long_keyword_lists_are_not_penalized():
    scorer = LexicalScorer(saturation=2)
    ranked = scorer.rank("schedule a meeting", [e.descriptor for e in reference_experts()])
    intent = next(s for s in ranked if s.expert_id == "intent_classifier")
    assert intent.score == 1.0


def test_phrase_keywords_match_on_word_boundaries():
    # "in french" must not match inside "ingrained french".
    ranked = LexicalScorer().rank("an ingrained french habit", [e.descriptor for e in reference_experts()])
    intent = next(s for s in ranked if s.expert_id == "intent_classifier")
    assert intent.matched == ()


def test_scorer_rejects_zero_saturation():
    with pytest.raises(ValueError, match="saturation"):
        LexicalScorer(saturation=0)


def test_labeled_fixture_loads_and_has_all_labels():
    rows = shadow.load_labeled(DATA)
    assert len(rows) >= 30
    assert {r.label for r in rows} == {"intent_classifier", "extractor", shadow.UNSURE}


def test_shadow_gate_passes_on_synthetic_set():
    report = shadow.evaluate(shadow.load_labeled(DATA), reference_experts(), LexicalScorer())
    assert report.passed, report.failures
    assert report.domains["intent"].precision == 1.0
    assert report.domains["extraction"].precision >= shadow.PRECISION_GATE
    assert report.structural_precision == 1.0


def test_shadow_gate_reports_the_known_false_positive():
    # The bare verb "find" routes a generic query to the extractor. The gate
    # tolerates it, and the report must still show it.
    report = shadow.evaluate(shadow.load_labeled(DATA), reference_experts(), LexicalScorer())
    assert report.unsure_correct == report.unsure_total - 1
    assert report.domains["extraction"].correct == report.domains["extraction"].predicted - 1


class _AlwaysFirst:
    """A deliberately poor scorer: always routes to the first candidate."""

    def decide(self, query, experts):
        from organism_sdk.moa.scorer import RouteDecision

        experts = list(experts)
        return RouteDecision(ROUTE_EXPERT, experts[0].descriptor.expert_id, (), 1.0, "always_first")


def test_shadow_gate_fails_for_a_poor_scorer():
    report = shadow.evaluate(shadow.load_labeled(DATA), reference_experts(), _AlwaysFirst())
    assert not report.passed
    assert any("precision" in f for f in report.failures)


def test_shadow_gate_requires_minimum_predictions_per_domain():
    rows = [shadow.LabeledQuery("schedule a meeting", None, "intent_classifier")]
    report = shadow.evaluate(rows, reference_experts(), LexicalScorer())
    assert not report.passed
    assert any("need 5" in f for f in report.failures)


def test_structural_baseline_flags_a_wrong_form_mapping():
    # Labeled as the extractor, but the form points at the intent classifier.
    rows = [shadow.LabeledQuery("find the numbers 1 and 2", "pattern_recognition", "extractor")]
    experts = reference_experts()
    report = shadow.evaluate(rows * 5, experts, LexicalScorer())
    assert report.structural_precision == 0.0
    assert not report.passed


def test_extra_expert_in_a_form_breaks_structural_determinism():
    # Two experts on one form: the structural baseline has no single choice and skips it.
    rows = [shadow.LabeledQuery("anything", "pattern_recognition", "intent_classifier")]
    report = shadow.evaluate(rows, reference_experts() + [_ConstantExpert()], LexicalScorer())
    assert report.structural_predicted == 0
