"""Pleurotus ostreatus mycelium substrate — exploration RESEARCH_TIER."""
from __future__ import annotations

import hashlib
from dataclasses import replace
import json
from typing import Any

from organism_sdk.contract import (
    BudgetClass,
    Channel,
    DataType,
    Determinism,
    HardwareRequirement,
    JustificationKind,
    Lifecycle,
    MaxSafetyTier,
    Modality,
    ModuleRole,
    OutputForm,
    ReliabilityTier,
    Shape,
    UncertaintyKind,
)
from organism_sdk.health import HealthReport
from organism_sdk.inputs import PerceptionInput
from organism_sdk.justification import Emission
from organism_sdk.module import OrganismModule
from _common.contract_factory import make_contract

from bio_digital.hal import BioDigitalHAL
from bio_digital.limits import (
    MYCELIUM_LIMITS,
    MYCELIUM_SPIKE_THRESHOLD,
    MYCELIUM_SYNAPTIC_WEIGHT,
    SPECIES_MYCELIUM,
)

MODULE_ID = "bio_digital.mycelium"
MODULE_VERSION = "1.1.0"
FMT = "typed-json:bio-mycelium/v1"


class MyceliumModule(OrganismModule):
    """Hyphal spike-train network memory twin. Never actuates."""

    def __init__(self, *, node_id: str = "mycelium-0", hal: BioDigitalHAL | None = None) -> None:
        self.node_id = node_id
        self.hal = hal or BioDigitalHAL(MYCELIUM_LIMITS, node_id=node_id)
        self._status = "HEALTHY"
        self._score = 1.0
        self._invocations = 0

    def declare_contract(self):
        c = make_contract(
            module_id=MODULE_ID,
            version=MODULE_VERSION,
            role=ModuleRole.PERCEPTION,
            tier=ReliabilityTier.T3_LEARNED_UNCALIBRATED,
            modalities=(Modality.PHYSICAL_SENSOR, Modality.DENSE_VECTOR),
            required_modalities=(Modality.PHYSICAL_SENSOR,),
            output_form=OutputForm.FEATURE_VECTOR,
            uncertainty=UncertaintyKind.ENSEMBLE_SPREAD,
            determinism=Determinism.STOCHASTIC,
            justification_kind=JustificationKind.NONE,
            justification_format=FMT,
            required_fields=(),
            may_actuate=False,
            requires_cross_check=True,
            max_safety=MaxSafetyTier.RESEARCH,
            budget=BudgetClass.RESEARCH,
            hardware=HardwareRequirement.PHYSICAL_SUBSTRATE,
            write_tags=("physical", "exploration", "bio_mycelium_result", "bio_twin"),
            read_tags=("*",),
            failure_name="desiccation_risk",
            health_port=8782,
            shape_dims=(8,),
        )
        return replace(
            c,
            channels=(
                Channel(
                    channel_id="bio_digital.ipc.spatial_graph",
                    producer_module="bio_digital.bus",
                    consumer_modules=(MODULE_ID,),
                    payload_modality=Modality.DENSE_VECTOR,
                    payload_shape=Shape(dims=(8,), dtype=DataType.FP32),
                    delivery="AT_LEAST_ONCE",
                    logged_for_trace=True,
                ),
                Channel(
                    channel_id="bio_digital.ipc.heartbeat",
                    producer_module=MODULE_ID,
                    consumer_modules=("bio_digital.hypervisor",),
                    payload_modality=Modality.DENSE_VECTOR,
                    payload_shape=Shape(dims=(1,), dtype=DataType.FP32),
                    logged_for_trace=True,
                ),
            ),
            lifecycle=Lifecycle(
                hot_swap_supported=True,
                shadow_validation_required=True,
                replaceable=True,
                self_termination_permitted=True,
            ),
        )

    def health(self) -> HealthReport:
        env = self.hal.read_telemetry()
        if not env.is_healthy:
            self._status = "DEGRADED"
            self._score = 0.3
        else:
            self._status = "HEALTHY"
            self._score = 1.0
        return HealthReport(module_id=MODULE_ID, status=self._status, score=self._score)

    def process_spike_train(self, spikes: list[float]) -> list[float]:
        env = self.hal.read_telemetry()
        if not env.is_healthy:
            raise RuntimeError("life_support_compromised")
        out: list[float] = []
        for index, spike in enumerate(spikes):
            clamped = min(float(spike), self.hal.limits.max_voltage)
            self.hal.apply_potential(f"PROBE_{index}", clamped)
            integrated = clamped * MYCELIUM_SYNAPTIC_WEIGHT
            out.append(1.0 if integrated > MYCELIUM_SPIKE_THRESHOLD else 0.0)
        return out

    def handle(self, input: PerceptionInput) -> Emission:
        if input.task_descriptor.form == "control_actuation":
            body = json.dumps(
                {
                    "refused": True,
                    "reason": "bio_digital_never_control_path",
                    "species": SPECIES_MYCELIUM,
                    "research_sim": True,
                },
                sort_keys=True,
            ).encode()
            return Emission(
                action_class="hold",
                payload=body,
                metadata={"module_id": MODULE_ID, "may_actuate": "False"},
            )
        self._invocations += 1
        spikes = [0.4, 0.2, 0.5]
        payload = input.modalities.get(Modality.DENSE_VECTOR)
        if payload is not None and payload.data:
            spikes = [b / 255.0 for b in payload.data[:8]]
        result = self.process_spike_train(spikes)
        twin = self.hal.sample_twin()
        body_obj: dict[str, Any] = {
            "species": SPECIES_MYCELIUM,
            "spikes_in": spikes,
            "spikes_out": result,
            "twin": twin,
            "exploration_only": True,
            "hypothesis_id": hashlib.sha256(
                f"{self._invocations}:{input.task_descriptor.task_id}".encode()
            ).hexdigest()[:12],
        }
        return Emission(
            action_class="exploration",
            payload=json.dumps(body_obj, sort_keys=True).encode(),
            metadata={"module_id": MODULE_ID, "research_sim": "True"},
        )
