"""Physarum polycephalum slime-mold substrate — exploration RESEARCH_TIER."""
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
from bio_digital.limits import PHYSARUM_LIMITS, PHYSARUM_LOGIC_VOLTAGE, SPECIES_PHYSARUM

MODULE_ID = "bio_digital.slime_mold"
MODULE_VERSION = "1.1.0"
FMT = "typed-json:bio-slime/v1"


class SlimeMoldModule(OrganismModule):
    """Spatial / XOR-style pathfinding solver via Physarum twin. Never actuates."""

    def __init__(self, *, node_id: str = "slime-0", hal: BioDigitalHAL | None = None) -> None:
        self.node_id = node_id
        self.hal = hal or BioDigitalHAL(PHYSARUM_LIMITS, node_id=node_id)
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
            write_tags=("physical", "exploration", "bio_slime_result", "bio_twin"),
            read_tags=("*",),
            failure_name="thermal_breach",
            health_port=8781,
            shape_dims=(2,),
        )
        return replace(
            c,
            channels=(
                Channel(
                    channel_id="bio_digital.ipc.spike_train",
                    producer_module="bio_digital.bus",
                    consumer_modules=(MODULE_ID,),
                    payload_modality=Modality.DENSE_VECTOR,
                    payload_shape=Shape(dims=(2,), dtype=DataType.FP32),
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

    def execute_logic_gate(self, input_a: float, input_b: float) -> float:
        """Chemotactic XOR via electrode stim (sim twin)."""
        env = self.hal.read_telemetry()
        if not env.is_healthy:
            raise RuntimeError("life_support_compromised")
        vol_a = PHYSARUM_LOGIC_VOLTAGE if input_a > 0 else 0.0
        vol_b = PHYSARUM_LOGIC_VOLTAGE if input_b > 0 else 0.0
        self.hal.apply_potential("VALVE_A", vol_a)
        self.hal.apply_potential("VALVE_B", vol_b)
        return float(bool(input_a) ^ bool(input_b))

    def handle(self, input: PerceptionInput) -> Emission:
        if input.task_descriptor.form == "control_actuation":
            body = json.dumps(
                {
                    "refused": True,
                    "reason": "bio_digital_never_control_path",
                    "species": SPECIES_PHYSARUM,
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
        # Optional vector inputs as gate operands
        a, b = 1.0, 0.0
        payload = input.modalities.get(Modality.DENSE_VECTOR)
        if payload is not None and payload.data:
            # interpret first two bytes as presence flags
            a = 1.0 if payload.data[0] else 0.0
            b = 1.0 if (len(payload.data) > 1 and payload.data[1]) else 0.0
        result = self.execute_logic_gate(a, b)
        twin = self.hal.sample_twin()
        body_obj: dict[str, Any] = {
            "species": SPECIES_PHYSARUM,
            "gate": "XOR",
            "inputs": [a, b],
            "result": result,
            "twin": twin,
            "exploration_only": True,
            "hypothesis_id": hashlib.sha256(
                f"{self._invocations}:{input.task_descriptor.task_id}:{result}".encode()
            ).hexdigest()[:12],
        }
        return Emission(
            action_class="exploration",
            payload=json.dumps(body_obj, sort_keys=True).encode(),
            metadata={"module_id": MODULE_ID, "research_sim": "True"},
        )
