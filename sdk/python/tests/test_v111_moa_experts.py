"""v1.11 MoA experts: descriptors, contracts, registration, and reference answers."""

from __future__ import annotations

import json

import pytest
from organism_sdk.contract import ModuleRole, Severity
from organism_sdk.health import HealthReport
from organism_sdk.moa.experts import (
    BaseExpert,
    CapabilityDescriptor,
    ExpertOutput,
    register_experts,
)
from organism_sdk.moa.reference import Extractor, IntentClassifier, reference_experts
from organism_sdk.registry import RegistryClient


def _descriptor(**overrides) -> CapabilityDescriptor:
    base = {
        "expert_id": "probe",
        "domain": "probe",
        "task_forms": ("pattern_recognition",),
        "keywords": ("probe",),
        "role": ModuleRole.PREDICTION,
    }
    base.update(overrides)
    return CapabilityDescriptor(**base)


def test_descriptor_rejects_unknown_form():
    with pytest.raises(ValueError, match="unknown task form"):
        _descriptor(task_forms=("not_a_form",))


def test_descriptor_rejects_role_not_eligible_for_form():
    # pattern_recognition allows PERCEPTION and PREDICTION, not ACTUATOR.
    with pytest.raises(ValueError, match="not eligible"):
        _descriptor(role=ModuleRole.ACTUATOR)


def test_descriptor_requires_keywords_and_forms():
    with pytest.raises(ValueError, match="keyword"):
        _descriptor(keywords=())
    with pytest.raises(ValueError, match="task form"):
        _descriptor(task_forms=())


def test_descriptor_rejects_non_positive_latency():
    with pytest.raises(ValueError, match="positive"):
        _descriptor(expected_latency_ms=0.0)


def test_output_confidence_must_be_unit_interval():
    with pytest.raises(ValueError, match="confidence"):
        ExpertOutput("x", "{}", 1.5, schema_valid=True)


def test_reference_experts_declare_valid_contracts():
    for expert in reference_experts():
        issues = expert.declare_contract().validate()
        errors = [i for i in issues if i.severity == Severity.ERROR]
        assert errors == [], (expert.module_id, errors)


def test_reference_experts_are_cpu_only_and_non_actuating():
    for expert in reference_experts():
        contract = expert.declare_contract()
        assert contract.safety.may_actuate is False
        assert expert.descriptor.requires_gpu is False


def test_register_experts_lands_in_exploration_and_queries_back():
    registry = RegistryClient()
    responses = register_experts(registry, reference_experts())
    assert [r.initial_state for r in responses] == ["EXPLORATION", "EXPLORATION"]
    assert all(r.validation_issues == [] for r in responses)
    assert sorted(registry.list_module_ids()) == ["moa.extractor", "moa.intent_classifier"]


def test_registry_health_reports_healthy_then_failed():
    registry = RegistryClient()
    experts = reference_experts()
    register_experts(registry, experts)
    assert registry.health("moa.extractor").status == "HEALTHY"
    experts[1].fail()
    assert registry.health("moa.extractor").status == "FAILED"
    experts[1].restore()
    assert registry.health("moa.extractor").status == "HEALTHY"


def test_intent_classifier_picks_best_intent_with_evidence_share():
    out = IntentClassifier().answer("Please schedule a meeting and remind me")
    body = json.loads(out.payload)
    assert body["intent"] == "schedule"
    assert body["matched"] == ["schedule", "meeting"]
    assert out.confidence == pytest.approx(2 / 3)
    assert out.schema_valid is True


def test_intent_classifier_reports_no_intent_with_zero_confidence():
    out = IntentClassifier().answer("Good morning")
    assert json.loads(out.payload)["intent"] == "none"
    assert out.confidence == 0.0
    assert out.schema_valid is True


def test_extractor_finds_dates_emails_and_numbers_without_double_counting():
    out = Extractor().answer("Extract 2026-11-05, a@b.co and the numbers 3.5 and 42")
    body = json.loads(out.payload)
    assert body == {"dates": ["2026-11-05"], "emails": ["a@b.co"], "numbers": ["3.5", "42"]}
    assert out.confidence == 1.0
    assert out.schema_valid is True


def test_extractor_with_nothing_to_extract_has_zero_confidence():
    out = Extractor().answer("nothing structured here")
    assert out.confidence == 0.0
    assert out.schema_valid is True


class _ConstantExpert(BaseExpert):
    """Test double: returns a fixed output, so schema and health paths can be driven."""

    def __init__(self, payload: str, schema_valid: bool, confidence: float = 0.5) -> None:
        super().__init__(_descriptor(expert_id="constant", domain="constant", keywords=("constant",)))
        self._output = ExpertOutput("constant", payload, confidence, schema_valid)

    def answer(self, query: str, form: str | None = None) -> ExpertOutput:
        return self._output


def test_base_expert_health_report_type():
    report = _ConstantExpert("{}", True).health()
    assert isinstance(report, HealthReport)
    assert report.module_id == "moa.constant"
