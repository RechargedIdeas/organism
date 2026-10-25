"""snn_sentinel — T1 SENTINEL with NEUROMORPHIC hardware requirement (v0.3-M4).

Corpus rule: on boxes without neuromorphic silicon the module may register
but must not be dispatched on the production control path unless
NEUROMORPHIC is available (or ORGANISM_NEURO_SIM=1). The spike-rate simulator
itself always runs on CPU (v1.3 CPU Everywhere). Crossing threshold emits an
event-driven wake into the workspace and can escalate the router.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

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
from organism_sdk.health import HealthReport
from organism_sdk.hypervector import Hypervector
from organism_sdk.inputs import PerceptionInput
from organism_sdk.justification import Emission
from organism_sdk.module import OrganismModule
from organism_sdk.workspace import BindingRecord, WorkspaceClient
from organism_sdk.neuro_sim import neuro_sim_enabled

MODULE_ID = "snn_sentinel"
MODULE_VERSION = "0.3.0"
SPIKE_WAKE_TAG = "snn_spike_wake"


@dataclass
class SpikeState:
    rate_hz: float = 0.0
    threshold_hz: float = 100.0
    last_wake_at: datetime | None = None
    wake_count: int = 0


class SNNSentinel(OrganismModule):
    """Event-driven sentinel. Hardware-gated for production dispatch."""

    def __init__(
        self,
        *,
        workspace: WorkspaceClient | None = None,
        spike_threshold_hz: float = 100.0,
        hardware_present: bool | None = None,
    ) -> None:
        self._ws = workspace
        self._spikes = SpikeState(threshold_hz=spike_threshold_hz)
        # ORGANISM_NEURO_SIM=1 => treat as present (RESEARCH_SIM); explicit False wins
        if hardware_present is None:
            hardware_present = neuro_sim_enabled()
        self.hardware_present = bool(hardware_present)
        self.research_sim = neuro_sim_enabled()
        self._status = "HEALTHY"

    def declare_contract(self) -> SubstrateContract:
        return SubstrateContract(
            identity=Identity(
                module_id=MODULE_ID,
                version=MODULE_VERSION,
                author="organism-ref",
                license="Apache-2.0",
                role=ModuleRole.SENTINEL,
                artifact_digest=hashlib.sha256(b"snn_sentinel:0.3.0").digest(),
            ),
            perception=PerceptionSignature(
                modalities=(Modality.SPIKE_TRAIN, Modality.TEMPORAL_STREAM),
                required_modalities=(Modality.SPIKE_TRAIN,),
                shapes={"SPIKE_TRAIN": Shape(dims=(1,), dtype=DataType.FP32)},
            ),
            emission=EmissionSignature(
                output_form=OutputForm.SPIKE_TRAIN,
                shape=Shape(dims=(1,), dtype=DataType.FP32),
                uncertainty=UncertaintyKind.NONE,
                determinism=Determinism.SEEDED,
                requires_justification_for=(),
            ),
            metabolic=MetabolicProfile(
                latency_p50_ms=0.5,
                latency_p95_ms=2.0,
                latency_p99_ms=5.0,
                energy_per_inference_j=0.001,
                memory_footprint_mb=32.0,
                memory_peak_mb=64.0,
                metabolic_budget_class=BudgetClass.LEAN,
                declared_share=ResourceVector(cpu_cores=0.25, memory_mb=64.0),
                requires_special_hardware=HardwareRequirement.NEUROMORPHIC,
            ),
            failure=FailureSignature(
                modes=(
                    FailureMode(
                        name="spike_silence",
                        observable_signal="rate_hz",
                        expected_degradation=DegradationKind.SPIKE_SILENCE,
                        detection_latency_budget_ms=100.0,
                    ),
                ),
                probe=HealthProbe(
                    HealthHttp(url="http://127.0.0.1:8777/health", timeout_ms=200)
                ),
                recovery=RecoveryProcedure(kind=RecoveryKind.RESTART),
                escalation=HealthEscalationPolicy(
                    kind=EscalationKind.PROBE_OR_DURATION,
                    consecutive_probe_failures=3,
                    degraded_duration_ms=5_000,
                    escalate_on_probe_unreachable=False,
                    probe_interval_ms=1_000,
                    escalate_on_probe_timeout=True,
                ),
            ),
            safety=SafetyDeclaration(
                reliability_tier=ReliabilityTier.T1_CALIBRATED_NONLEARNED,
                may_actuate=False,
                requires_cross_check=True,
                cross_check_eligible_roles=(ModuleRole.VERIFIER, ModuleRole.GOVERNANCE),
                max_safety_tier=MaxSafetyTier.HIGH,
            ),
            lifecycle=Lifecycle(shadow_validation_required=True),
            capabilities=CapabilityScopes(
                read_roles=("sentinel",),
                write_roles=("sentinel",),
                read_tags=("*",),
                write_tags=("sentinel", SPIKE_WAKE_TAG),
            ),
            justification=JustificationSpec(
                kind=JustificationKind.NONE,
                format="",
                checkable_by=(ModuleRole.VERIFIER,),
            ),
        )

    def health(self) -> HealthReport:
        return HealthReport(module_id=MODULE_ID, status=self._status, score=1.0)

    def simulate_spikes(self, rate_hz: float) -> dict[str, Any]:
        """Software spike-rate simulator (no neuromorphic required)."""
        self._spikes.rate_hz = float(rate_hz)
        woke = rate_hz >= self._spikes.threshold_hz
        result: dict[str, Any] = {
            "rate_hz": rate_hz,
            "threshold_hz": self._spikes.threshold_hz,
            "wake": woke,
            "hardware_present": self.hardware_present,
        }
        if woke:
            self._spikes.wake_count += 1
            self._spikes.last_wake_at = datetime.now(timezone.utc)
            binding = self.emit_wake(rate_hz)
            result["binding_id"] = str(binding.binding_id) if binding else None
        return result

    def emit_wake(self, rate_hz: float) -> BindingRecord | None:
        if self._ws is None:
            return None
        role = Hypervector.random(seed=0x534E4E00)
        filler = Hypervector.random()
        rec = BindingRecord(
            binding_id=uuid.uuid4(),
            hypervector=role.bind(filler),
            role=role,
            filler=filler,
            tags=(SPIKE_WAKE_TAG, "sentinel"),
            module_id=MODULE_ID,
            salience=0.9,
            fidelity="FULL",
            payload={
                "rate_hz": rate_hz,
                "threshold_hz": self._spikes.threshold_hz,
                "at": datetime.now(timezone.utc).isoformat(),
                "simulated": True,
                "hardware_present": self.hardware_present,
                "research_sim": self.research_sim,
            },
            affects_control=False,  # wake is advisory until router escalates
        )
        self._ws.write(rec)
        return rec

    def handle(self, input: PerceptionInput) -> Emission:
        # Without hardware, handle is simulation-only and must not claim actuation
        rate = self._spikes.rate_hz
        body = f'{{"rate_hz":{rate},"simulated":true}}'.encode()
        return Emission(
            action_class=input.task_descriptor.form,
            payload=body,
            metadata={"hardware_present": str(self.hardware_present)},
        )

    def on_drain(self, deadline: datetime) -> None:
        return None
