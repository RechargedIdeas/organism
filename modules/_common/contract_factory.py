"""Thin SubstrateContract factory for reference modules (IMP-22)."""
from __future__ import annotations

import hashlib
from typing import Sequence

from organism_sdk.contract import (
    BudgetClass,
    CapabilityScopes,
    DataType,
    DegradationKind,
    Determinism,
    EmissionSignature,
    EscalationKind,
    FailureMode,
    FailureSignature,
    HardwareRequirement,
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
    RecoveryKind,
    RecoveryProcedure,
    ReliabilityTier,
    ResourceVector,
    SafetyDeclaration,
    Shape,
    SubstrateContract,
    UncertaintyKind,
)


def digest_of(s: str) -> bytes:
    return hashlib.sha256(s.encode()).digest()


def make_contract(
    *,
    module_id: str,
    version: str,
    role: ModuleRole,
    tier: ReliabilityTier,
    modalities: Sequence[Modality],
    required_modalities: Sequence[Modality],
    output_form: OutputForm,
    uncertainty: UncertaintyKind,
    determinism: Determinism,
    justification_kind: JustificationKind,
    justification_format: str,
    required_fields: Sequence[str],
    may_actuate: bool = False,
    requires_cross_check: bool = False,
    requires_causal_certificate: bool = False,
    max_safety: MaxSafetyTier = MaxSafetyTier.HIGH,
    requires_justification_for: Sequence[str] = (),
    write_tags: Sequence[str] = ("memory",),
    read_tags: Sequence[str] = ("*",),
    budget: BudgetClass = BudgetClass.LEAN,
    hardware: HardwareRequirement = HardwareRequirement.NONE,
    health_port: int = 8765,
    shape_dims: tuple[int, ...] = (8,),
    dtype: DataType = DataType.FP32,
    failure_name: str = "timeout",
    failure_kind: DegradationKind = DegradationKind.TIMEOUT,
) -> SubstrateContract:
    shapes = {
        m.name: Shape(dims=shape_dims, dtype=dtype) for m in modalities
    }
    url = f"http://127.0.0.1:{health_port}/health"
    return SubstrateContract(
        identity=Identity(
            module_id=module_id,
            version=version,
            author="organism-ref",
            license="Apache-2.0",
            role=role,
            artifact_digest=digest_of(f"{module_id}:{version}"),
        ),
        perception=PerceptionSignature(
            modalities=tuple(modalities),
            required_modalities=tuple(required_modalities),
            shapes=shapes,
        ),
        emission=EmissionSignature(
            output_form=output_form,
            shape=Shape(dims=shape_dims, dtype=dtype),
            uncertainty=uncertainty,
            determinism=determinism,
            requires_justification_for=tuple(requires_justification_for),
        ),
        metabolic=MetabolicProfile(
            latency_p50_ms=2.0,
            latency_p95_ms=8.0,
            latency_p99_ms=20.0,
            energy_per_inference_j=0.002,
            memory_footprint_mb=64.0,
            memory_peak_mb=128.0,
            metabolic_budget_class=budget,
            declared_share=ResourceVector(cpu_cores=0.5, memory_mb=128.0),
            requires_special_hardware=hardware,
        ),
        failure=FailureSignature(
            modes=(
                FailureMode(
                    name=failure_name,
                    observable_signal="module.alive",
                    expected_degradation=failure_kind,
                    detection_latency_budget_ms=1000.0,
                ),
            ),
            probe=HealthProbe(HealthHttp(url=url, expected_status="200", timeout_ms=400)),
            recovery=RecoveryProcedure(kind=RecoveryKind.RESTART, max_attempts=3),
            escalation=HealthEscalationPolicy(
                kind=EscalationKind.PROBE_OR_DURATION,
                consecutive_probe_failures=2,
                degraded_duration_ms=5000,
                escalate_on_probe_timeout=True,
                escalate_on_probe_unreachable=False,
                probe_interval_ms=1000,
            ),
        ),
        safety=SafetyDeclaration(
            reliability_tier=tier,
            may_actuate=may_actuate,
            requires_causal_certificate=requires_causal_certificate,
            requires_cross_check=requires_cross_check,
            max_safety_tier=max_safety,
        ),
        lifecycle=Lifecycle(
            hot_swap_supported=True,
            shadow_validation_required=tier
            in (ReliabilityTier.T2_LEARNED_CALIBRATED, ReliabilityTier.T3_LEARNED_UNCALIBRATED),
        ),
        capabilities=CapabilityScopes(
            read_roles=("memory", "governance"),
            write_roles=("memory",),
            read_tags=tuple(read_tags),
            write_tags=tuple(write_tags),
            can_emit_control_affecting=may_actuate,
        ),
        justification=JustificationSpec(
            kind=justification_kind,
            format=justification_format,
            required_fields=tuple(required_fields),
            checkable_by=(ModuleRole.VERIFIER, ModuleRole.GOVERNANCE),
        ),
    )
