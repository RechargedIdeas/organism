"""v1.11 MoA capability routing: scorer decisions and the Phase 2 shadow gate."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest
from organism_sdk.contract import ModuleRole
from organism_sdk.moa import shadow
from organism_sdk.moa.experts import BaseExpert, CapabilityDescriptor, Expert, ExpertOutput
from organism_sdk.moa.reference import reference_experts
from organism_sdk.moa.scorer import (
    ROUTE_EXPERT,
    ROUTE_LLM_FALLBACK,
    ROUTE_UNSURE,
    LexicalScorer,
    RouteDecision,
)

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


def test_clear_leader_routes_to_expert() -> None:
    decision = LexicalScorer().decide("Extract the dates and numbers", reference_experts())
    assert decision.route == ROUTE_EXPERT
    assert decision.expert_id == "extractor"
    assert decision.reason == "clear_leader"


def test_no_keyword_evidence_is_unsure_by_default() -> None:
    decision = LexicalScorer().decide("Good morning", reference_experts())
    assert decision.route == ROUTE_UNSURE
    assert decision.expert_id is None
    assert decision.reason == "no_expert_clears_min_score"


def test_no_keyword_evidence_routes_to_llm_fallback_only_when_enabled() -> None:
    scorer = LexicalScorer(allow_llm_fallback=True)
    decision = scorer.decide("Good morning", reference_experts())
    assert decision.route == ROUTE_LLM_FALLBACK


def test_ambiguous_top_two_is_unsure() -> None:
    # "extract" hits the extractor and "remind" hits the intent classifier, one each.
    decision = LexicalScorer().decide("Extract and remind me", reference_experts())
    assert decision.route == ROUTE_UNSURE
    assert decision.reason == "ambiguous_top_two"


def test_no_candidates_is_unsure() -> None:
    decision = LexicalScorer().decide("anything", [])
    assert decision.route == ROUTE_UNSURE
    assert decision.reason == "no_candidates"


def test_scoring_saturates_so_long_keyword_lists_are_not_penalized() -> None:
    scorer = LexicalScorer(saturation=2)
    ranked = scorer.rank("schedule a meeting", [e.descriptor for e in reference_experts()])
    intent = next(s for s in ranked if s.expert_id == "intent_classifier")
    assert intent.score == 1.0


def test_phrase_keywords_match_on_word_boundaries() -> None:
    # "in french" must not match inside "ingrained french".
    ranked = LexicalScorer().rank("an ingrained french habit", [e.descriptor for e in reference_experts()])
    intent = next(s for s in ranked if s.expert_id == "intent_classifier")
    assert intent.matched == ()


def test_scorer_rejects_zero_saturation() -> None:
    with pytest.raises(ValueError, match="saturation"):
        LexicalScorer(saturation=0)


def test_labeled_fixture_loads_and_has_all_labels() -> None:
    rows = shadow.load_labeled(DATA)
    assert len(rows) >= 30
    assert {r.label for r in rows} == {"intent_classifier", "extractor", shadow.UNSURE}


def test_shadow_gate_passes_on_synthetic_set() -> None:
    report = shadow.evaluate(shadow.load_labeled(DATA), reference_experts(), LexicalScorer())
    assert report.passed, report.failures
    assert report.domains["intent"].precision == 1.0
    extraction = report.domains["extraction"].precision
    assert extraction is not None
    assert extraction >= shadow.PRECISION_GATE
    assert report.structural_precision == 1.0


def test_bare_find_does_not_route_generic_queries_to_the_extractor() -> None:
    # Before the fix, "find" alone sent generic queries to the extractor (held-out precision 0.78).
    decision = LexicalScorer().decide("Find a good recipe for dinner", reference_experts())
    assert decision.route == ROUTE_UNSURE


def test_shadow_gate_passes_on_held_out_set() -> None:
    # Written with labels fixed from each query's meaning, before any scorer change was measured.
    heldout = Path(__file__).parent / "data" / "moa_routing_heldout.json"
    report = shadow.evaluate(shadow.load_labeled(heldout), reference_experts(), LexicalScorer())
    assert report.passed, report.failures
    assert (report.domains["extraction"].precision or 0.0) >= shadow.PRECISION_GATE


def test_email_addresses_beside_a_retrieval_verb_are_routed_to_extractor() -> None:
    # The O4 context rule: "email address(es)" counts for the extractor only beside a verb of retrieval.
    decision = LexicalScorer().decide("Pull the email addresses out of this list", reference_experts())
    assert decision.route == ROUTE_EXPERT
    assert decision.expert_id == "extractor"


class _AlwaysFirst:
    """A deliberately poor scorer: always routes to the first candidate."""

    def decide(self, query: str, experts: Iterable[Expert]) -> RouteDecision:
        candidates = list(experts)
        return RouteDecision(ROUTE_EXPERT, candidates[0].descriptor.expert_id, (), 1.0, "always_first")


def test_shadow_gate_fails_for_a_poor_scorer() -> None:
    report = shadow.evaluate(shadow.load_labeled(DATA), reference_experts(), _AlwaysFirst())
    assert not report.passed
    assert any("precision" in f for f in report.failures)


def test_shadow_gate_requires_minimum_predictions_per_domain() -> None:
    rows = [shadow.LabeledQuery("schedule a meeting", None, "intent_classifier")]
    report = shadow.evaluate(rows, reference_experts(), LexicalScorer())
    assert not report.passed
    assert any("need 5" in f for f in report.failures)


def test_structural_baseline_flags_a_wrong_form_mapping() -> None:
    # Labeled as the extractor, but the form points at the intent classifier.
    rows = [shadow.LabeledQuery("find the numbers 1 and 2", "pattern_recognition", "extractor")]
    experts = reference_experts()
    report = shadow.evaluate(rows * 5, experts, LexicalScorer())
    assert report.structural_precision == 0.0
    assert not report.passed


def test_extra_expert_in_a_form_breaks_structural_determinism() -> None:
    # Two experts on one form: the structural baseline has no single choice and skips it.
    rows = [shadow.LabeledQuery("anything", "pattern_recognition", "intent_classifier")]
    report = shadow.evaluate(rows, reference_experts() + [_ConstantExpert()], LexicalScorer())
    assert report.structural_predicted == 0
