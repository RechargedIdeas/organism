"""v0.4-M3 — Security / trust-model fuzz helpers (fixed seeds)."""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from deterministic_engine.engine import DeterministicEngine
from learned_module.module import LearnedModule
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
from organism_sdk.degradation import BYZ_COUNT_L4, DegradationMachine, FaultInjector, HealthSignals, T_DOWN_FAST
from organism_sdk.errors import JustificationMissing, RegistrationRejected
from organism_sdk.hypervector import Hypervector
from organism_sdk.immune import IMMUNE_MODULE_ID, ImmuneLayer, validate_control_binding
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.justification import Emission
from organism_sdk.module import OrganismModule, run_handle
from organism_sdk.registry import RegistryClient
from organism_sdk.router import Router, RouterTask
from organism_sdk.workspace import BindingRecord, WorkspaceClient


def _minimal_failure() -> FailureSignature:
    return FailureSignature(
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


def malformed_contract_empty_identity() -> SubstrateContract:
    return SubstrateContract(
        identity=Identity(
            module_id="",
            version="",
            author="x",
            license="Apache-2.0",
            role=ModuleRole.GOVERNANCE,
            artifact_digest=b"\x00" * 32,
        ),
        perception=PerceptionSignature(modalities=(Modality.TABULAR,), required_modalities=(Modality.TABULAR,)),
        emission=EmissionSignature(
            output_form=OutputForm.SCALAR,
            shape=Shape(dims=(1,), dtype=DataType.FP32),
            uncertainty=UncertaintyKind.NONE,
            determinism=Determinism.DETERMINISTIC,
        ),
        metabolic=MetabolicProfile(
            latency_p50_ms=1, latency_p95_ms=2, latency_p99_ms=3,
            energy_per_inference_j=0.001, memory_footprint_mb=8, memory_peak_mb=16,
        ),
        failure=_minimal_failure(),
        safety=SafetyDeclaration(
            reliability_tier=ReliabilityTier.T0_DETERMINISTIC,
            may_actuate=False,
            max_safety_tier=MaxSafetyTier.LOW,
        ),
        lifecycle=Lifecycle(),
        capabilities=CapabilityScopes(),
    )


def malformed_contract_required_modality_undeclared() -> SubstrateContract:
    return SubstrateContract(
        identity=Identity(
            module_id="bad.mod",
            version="0.0.1",
            author="x",
            license="Apache-2.0",
            role=ModuleRole.PERCEPTION,
            artifact_digest=b"\x01" * 32,
        ),
        perception=PerceptionSignature(
            modalities=(Modality.TABULAR,),
            required_modalities=(Modality.IMAGE,),  # undeclared
        ),
        emission=EmissionSignature(
            output_form=OutputForm.FEATURE_VECTOR,
            shape=Shape(dims=(4,), dtype=DataType.FP32),
            uncertainty=UncertaintyKind.NONE,
            determinism=Determinism.SEEDED,
        ),
        metabolic=MetabolicProfile(
            latency_p50_ms=1, latency_p95_ms=2, latency_p99_ms=3,
            energy_per_inference_j=0.001, memory_footprint_mb=8, memory_peak_mb=16,
        ),
        failure=_minimal_failure(),
        safety=SafetyDeclaration(
            reliability_tier=ReliabilityTier.T3_LEARNED_UNCALIBRATED,
            may_actuate=False,
            max_safety_tier=MaxSafetyTier.RESEARCH,
        ),
        lifecycle=Lifecycle(),
        capabilities=CapabilityScopes(),
    )


class _UnjustifiedActuator(OrganismModule):
    """Learned-style module that emits control_actuation without a token."""

    def declare_contract(self) -> SubstrateContract:
        return SubstrateContract(
            identity=Identity(
                module_id="fuzz.unjustified",
                version="0.0.1",
                author="fuzz",
                license="Apache-2.0",
                role=ModuleRole.ACTUATOR,
                artifact_digest=b"\x02" * 32,
            ),
            perception=PerceptionSignature(
                modalities=(Modality.DENSE_VECTOR,),
                required_modalities=(Modality.DENSE_VECTOR,),
            ),
            emission=EmissionSignature(
                output_form=OutputForm.SCALAR,
                shape=Shape(dims=(1,), dtype=DataType.FP32),
                uncertainty=UncertaintyKind.NONE,
                determinism=Determinism.STOCHASTIC,
                requires_justification_for=("control_actuation",),
            ),
            metabolic=MetabolicProfile(
                latency_p50_ms=1, latency_p95_ms=2, latency_p99_ms=3,
                energy_per_inference_j=0.001, memory_footprint_mb=8, memory_peak_mb=16,
            ),
            failure=_minimal_failure(),
            safety=SafetyDeclaration(
                reliability_tier=ReliabilityTier.T3_LEARNED_UNCALIBRATED,
                may_actuate=True,
                requires_cross_check=True,
                max_safety_tier=MaxSafetyTier.HIGH,
            ),
            lifecycle=Lifecycle(),
            capabilities=CapabilityScopes(),
            justification=JustificationSpec(kind=JustificationKind.KERNEL_BOUND, format="typed-json:kernel-bound/v1"),
        )

    def handle(self, input: PerceptionInput) -> Emission:  # noqa: A002
        return Emission(action_class="control_actuation", payload={"ok": False}, metadata={})

    def health(self):
        from organism_sdk.health import HealthReport

        return HealthReport(status="HEALTHY", detail={})

    def justify(self, emission: Emission):
        return None  # deliberately missing


@dataclass
class FuzzStats:
    trials: int
    rejected_contracts: int
    rejected_forgeries: int
    justification_blocks: int


def fuzz_malformed_contracts(seed: int = 0x564F3433, trials: int = 32) -> FuzzStats:
    rng = random.Random(seed)
    rejected = 0
    for i in range(trials):
        choice = rng.randrange(3)
        if choice == 0:
            c = malformed_contract_empty_identity()
        elif choice == 1:
            c = malformed_contract_required_modality_undeclared()
        else:
            c = malformed_contract_empty_identity()
            # mutate digest length weirdness already covered; flip author empty
            object.__setattr__  # keep simple
            c = malformed_contract_required_modality_undeclared()
        errors = [x for x in c.validate() if x.severity == Severity.ERROR]
        if errors:
            rejected += 1
            try:
                c.require_valid()
                raise AssertionError("expected RegistrationRejected")
            except RegistrationRejected:
                pass
        else:
            raise AssertionError("expected ERROR issues")
    return FuzzStats(trials=trials, rejected_contracts=rejected, rejected_forgeries=0, justification_blocks=0)


def fuzz_immune_forgeries(seed: int = 0x494D4D46, trials: int = 40) -> FuzzStats:
    rng = random.Random(seed)
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    rejected = 0
    role = Hypervector.random(seed=seed)
    for i in range(trials):
        filler = Hypervector.random(seed=seed + 1 + i)
        hv = role.bind(filler)
        fidelity = rng.choice(["FULL", "PARTIAL", "DEGRADED"])
        affects = rng.choice([True, False])
        module_id = rng.choice([IMMUNE_MODULE_ID, "attacker", "learned_module_t2"])
        salience = rng.choice([1.0, 0.5, 0.0])
        # Only legitimate combo should accept
        legit = fidelity == "FULL" and affects and module_id == IMMUNE_MODULE_ID and salience >= 1.0
        rec = BindingRecord(
            binding_id=uuid4(),
            hypervector=hv,
            role=role,
            filler=filler,
            tags=("immune_decision", "immune_decision/quarantine"),
            module_id=module_id,
            salience=salience,
            fidelity=fidelity,
            payload={"decision": "QUARANTINE", "safety": {"affects_control": affects}},
            affects_control=affects,
        )
        result = ws.write(rec)
        if legit:
            assert result.status == "ACCEPTED"
            got = ws.read_by_binding_id(rec.binding_id)
            assert got is not None and validate_control_binding(got)
        else:
            assert result.status == "REJECTED"
            assert result.reason_code == "immune_forgery_rejected"
            rejected += 1
            assert not validate_control_binding(rec)
    return FuzzStats(trials=trials, rejected_contracts=0, rejected_forgeries=rejected, justification_blocks=0)
