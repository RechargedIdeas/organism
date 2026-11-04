"""v1.11 MoA pipeline: end-to-end routing, tier drills, and fallbacks."""

from __future__ import annotations

import json

import pytest
from organism_sdk.contract import ModuleRole
from organism_sdk.moa import MAX_EXPERTS_PER_REQUEST, MoAPipeline, MoATier, TierController
from organism_sdk.moa.experts import BaseExpert, CapabilityDescriptor, ExpertOutput
from organism_sdk.moa.pipeline import DETERMINISTIC_ID, ROUTE_DETERMINISTIC
from organism_sdk.moa.reference import Extractor, IntentClassifier, reference_experts
from organism_sdk.moa.scorer import ROUTE_EXPERT, ROUTE_LLM_FALLBACK, ROUTE_UNSURE

# Two reference experts score on this query: extractor (2 hits) leads intent (1 hit).
BOTH_ACTIVE = "Extract the dates and remind me"


class _Stub(BaseExpert):
    def __init__(
        self,
        expert_id: str,
        keywords: tuple[str, ...],
        *,
        requires_gpu: bool = False,
        valid: bool = True,
        latency_ms: float = 2.0,
    ) -> None:
        super().__init__(
            CapabilityDescriptor(
                expert_id=expert_id,
                domain=expert_id,
                task_forms=("pattern_recognition",),
                keywords=keywords,
                role=ModuleRole.PREDICTION,
                expected_latency_ms=latency_ms,
                requires_gpu=requires_gpu,
            )
        )
        self._valid = valid

    def answer(self, query: str, form: str | None = None) -> ExpertOutput:
        return ExpertOutput(self.descriptor.expert_id, json.dumps({"from": self.descriptor.expert_id}), 0.9, self._valid)


def _pipeline(extra=(), **kwargs) -> MoAPipeline:
    return MoAPipeline(list(reference_experts()) + list(extra), **kwargs)


def _reference(pipeline_experts_map: MoAPipeline, expert_id: str):
    return pipeline_experts_map._experts[expert_id]


def test_clear_query_runs_one_expert_at_full_tier_with_provenance() -> None:
    result = _pipeline().run("Schedule a meeting and remind me")
    assert result.route == ROUTE_EXPERT
    assert result.expert_id == "intent_classifier"
    assert result.tier == MoATier.T0
    assert result.ran == ("intent_classifier",)
    assert result.provenance_ok is True


def test_unsure_query_returns_no_answer_and_does_not_move_the_tier() -> None:
    pipeline = _pipeline()
    result = pipeline.run("Good morning")
    assert result.route == ROUTE_UNSURE
    assert result.tier is None
    assert result.payload is None
    assert pipeline.tier == MoATier.T0


def test_llm_fallback_route_passes_through_only_when_enabled() -> None:
    from organism_sdk.moa.scorer import LexicalScorer

    result = _pipeline(scorer=LexicalScorer(allow_llm_fallback=True)).run("Good morning")
    assert result.route == ROUTE_LLM_FALLBACK
    assert result.tier is None


def test_form_filter_limits_candidates() -> None:
    result = _pipeline().run("Extract the dates and remind me", form="feature_extraction")
    assert result.route == ROUTE_EXPERT
    assert result.expert_id == "extractor"
    assert result.active == ("extractor",)


def test_failure_drill_degrades_then_recovers_after_hysteresis() -> None:
    pipeline = _pipeline()
    intent = _reference(pipeline, "intent_classifier")

    assert pipeline.run(BOTH_ACTIVE).tier == MoATier.T0

    intent.fail()
    degraded = pipeline.run(BOTH_ACTIVE)
    assert degraded.tier == MoATier.T2
    assert degraded.ran == ("extractor",)
    assert degraded.provenance_ok is None

    intent.restore()
    assert pipeline.run(BOTH_ACTIVE).tier == MoATier.T2  # recovering 1/3
    assert pipeline.run(BOTH_ACTIVE).tier == MoATier.T2  # recovering 2/3
    recovered = pipeline.run(BOTH_ACTIVE)
    assert recovered.tier == MoATier.T0
    assert recovered.ran == ("extractor", "intent_classifier")
    assert recovered.provenance_ok is True


def test_all_active_experts_failing_falls_back_to_deterministic() -> None:
    pipeline = _pipeline()
    _reference(pipeline, "intent_classifier").fail()
    _reference(pipeline, "extractor").fail()
    result = pipeline.run(BOTH_ACTIVE)
    assert result.route == ROUTE_DETERMINISTIC
    assert result.tier == MoATier.T4
    assert result.expert_id == DETERMINISTIC_ID
    assert result.ran == ()


def test_latency_budget_excludes_slow_experts() -> None:
    # Intent is 3 ms and extractor is 4 ms. A 3.5 ms budget leaves only the intent classifier.
    result = _pipeline(latency_budget_ms=3.5).run(BOTH_ACTIVE)
    assert result.active == ("extractor", "intent_classifier")
    assert result.ran == ("intent_classifier",)
    assert result.tier == MoATier.T2


def test_gpu_blocked_expert_takes_the_cpu_tier_and_is_skipped() -> None:
    gpu = _Stub("render_gpu", ("render", "image", "picture"), requires_gpu=True)
    result = _pipeline(extra=[gpu], gpu_available=False).run("Render the image and remind me")
    assert result.active == ("render_gpu", "intent_classifier")
    assert result.ran == ("intent_classifier",)
    assert result.tier == MoATier.T3


def test_gpu_available_runs_the_gpu_expert_at_full_tier() -> None:
    gpu = _Stub("render_gpu", ("render", "image", "picture"), requires_gpu=True)
    result = _pipeline(extra=[gpu], gpu_available=True).run("Render the image and remind me")
    assert result.tier == MoATier.T0
    assert set(result.ran) == {"render_gpu", "intent_classifier"}


def test_schema_invalid_output_on_every_path_falls_back_to_deterministic() -> None:
    bad = _Stub("zebra", ("zebra",), valid=False)
    result = _pipeline(extra=[bad]).run("zebra facts")
    assert result.route == ROUTE_DETERMINISTIC
    assert result.tier == MoATier.T4
    assert result.reason == "no_valid_output"


def test_custom_deterministic_fallback_is_used() -> None:
    def fallback(query, form):
        return ExpertOutput("custom_fallback", json.dumps({"answer": "fixed"}), 1.0, True)

    pipeline = _pipeline(deterministic_fallback=fallback)
    _reference(pipeline, "intent_classifier").fail()
    _reference(pipeline, "extractor").fail()
    result = pipeline.run(BOTH_ACTIVE)
    assert result.expert_id == "custom_fallback"
    assert json.loads(result.payload) == {"answer": "fixed"}


def test_global_level_l4_forces_deterministic_even_when_healthy() -> None:
    result = _pipeline().run("Schedule a meeting", global_level="L4")
    assert result.route == ROUTE_DETERMINISTIC
    assert result.reason.endswith("global_level_L4")


def test_top_k_is_bounded_by_the_request_cap() -> None:
    with pytest.raises(ValueError, match="top_k"):
        _pipeline(top_k=0)
    with pytest.raises(ValueError, match="top_k"):
        _pipeline(top_k=MAX_EXPERTS_PER_REQUEST + 1)


def test_duplicate_expert_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        MoAPipeline([IntentClassifier(), IntentClassifier()])


def test_pipeline_accepts_a_shared_tier_controller() -> None:
    controller = TierController(recover_after=1)
    pipeline = _pipeline(controller=controller)
    _reference(pipeline, "extractor").fail()
    assert pipeline.run(BOTH_ACTIVE).tier == MoATier.T2
    assert controller.tier == MoATier.T2
    _reference(pipeline, "extractor").restore()
    assert pipeline.run(BOTH_ACTIVE).tier == MoATier.T0


def test_extractor_class_is_reachable_by_id() -> None:
    pipeline = MoAPipeline([Extractor()])
    assert pipeline.run("extract the numbers 1 and 2").expert_id == "extractor"
