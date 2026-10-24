"""contract:validate gate — A.2 / FailureSignature escalation invariants."""
from __future__ import annotations

import pytest

from organism_sdk.contract import (
    CapabilityScopes,
    DataType,
    DegradationKind,
    Determinism,
    EmissionSignature,
    EscalationKind,
    FailureMode,
    FailureSignature,
    HealthEscalationPolicy,
    HealthHttp,
    HealthProbe,
    Identity,
    JustificationKind,
    JustificationSpec,
    Lifecycle,
    MaxSafetyTier,
    MetabolicProfile,
    Modality,
    ModuleRole,
    OutputForm,
    PerceptionSignature,
    RecoveryProcedure,
    ReliabilityTier,
    SafetyDeclaration,
    Severity,
    Shape,
    SubstrateContract,
    UncertaintyKind,
)
from organism_sdk.errors import RegistrationRejected


def _base_contract(**fail_kw) -> SubstrateContract:
    failure = fail_kw.pop("failure", None)
    if failure is None:
        failure = FailureSignature(
            modes=(
                FailureMode(
                    name="crash",
                    observable_signal="alive",
                    expected_degradation=DegradationKind.CRASH,
                    detection_latency_budget_ms=500,
                ),
            ),
            probe=HealthProbe(HealthHttp(url="http://127.0.0.1:9/health", timeout_ms=400)),
            recovery=RecoveryProcedure(),
            escalation=HealthEscalationPolicy(
                kind=EscalationKind.PROBE_OR_DURATION,
                consecutive_probe_failures=2,
                degraded_duration_ms=5000,
                escalate_on_probe_unreachable=False,
                probe_interval_ms=1000,
            ),
        )
    return SubstrateContract(
        identity=Identity(
            module_id="test.mod",
            version="0.1.0",
            author="t",
            license="Apache-2.0",
            role=ModuleRole.GOVERNANCE,
            artifact_digest=b"\x00" * 32,
        ),
        perception=PerceptionSignature(modalities=(Modality.TABULAR,), required_modalities=(Modality.TABULAR,)),
        emission=EmissionSignature(
            output_form=OutputForm.SYMBOLIC_TRIPLE,
            shape=Shape(dims=(3,), dtype=DataType.INT64),
            uncertainty=UncertaintyKind.SYMBOLIC_PROOF,
            determinism=Determinism.DETERMINISTIC,
            requires_justification_for=("control_actuation",),
        ),
        metabolic=MetabolicProfile(
            latency_p50_ms=1, latency_p95_ms=2, latency_p99_ms=3,
            energy_per_inference_j=0.001, memory_footprint_mb=16, memory_peak_mb=32,
        ),
        failure=failure,
        safety=SafetyDeclaration(
            reliability_tier=ReliabilityTier.T0_DETERMINISTIC,
            may_actuate=True,
            max_safety_tier=MaxSafetyTier.HIGH,
        ),
        lifecycle=Lifecycle(),
        capabilities=CapabilityScopes(),
        justification=JustificationSpec(kind=JustificationKind.RULE_TRACE, format="typed-json:rule-trace/v1"),
    )


def test_contract_validate_green():
    c = _base_contract()
    issues = c.validate()
    errors = [i for i in issues if i.severity == Severity.ERROR]
    assert errors == []
    c.require_valid()


def test_reg8_timeout_vs_degraded():
    failure = FailureSignature(
        modes=(),
        probe=HealthProbe(HealthHttp(url="http://x/h", timeout_ms=20000)),
        recovery=RecoveryProcedure(),
        escalation=HealthEscalationPolicy(
            escalate_on_probe_timeout=True,
            degraded_duration_ms=15000,
            probe_interval_ms=25000,  # also trips REG-10
        ),
    )
    c = _base_contract(failure=failure)
    codes = {i.code for i in c.validate() if i.severity == Severity.ERROR}
    assert "escalation_policy_inconsistent" in codes


def test_reg9_degraded_vs_cadence():
    failure = FailureSignature(
        modes=(),
        probe=HealthProbe(HealthHttp(url="http://x/h", timeout_ms=100)),
        recovery=RecoveryProcedure(),
        escalation=HealthEscalationPolicy(
            degraded_duration_ms=1000,  # < 3*5000
            probe_interval_ms=5000,
        ),
    )
    c = _base_contract(failure=failure)
    with pytest.raises(RegistrationRejected):
        c.require_valid()


def test_to_proto_roundtrip_fields():
    c = _base_contract()
    proto = c.to_proto()
    assert proto.identity.module_id == "test.mod"
    assert proto.failure.escalation.escalate_on_probe_unreachable is False
    assert proto.failure.escalation.probe_interval_ms == 1000
