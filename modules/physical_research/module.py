"""physical_research — RESEARCH_SIM molecular/physical substrate (v1.0-E).

Registers with PHYSICAL_SUBSTRATE requirement. Exploration-only: never
control path / never may_actuate. Digital-twin telemetry stubs only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from organism_sdk.contract import (
    BudgetClass,
    Determinism,
    HardwareRequirement,
    JustificationKind,
    MaxSafetyTier,
    Modality,
    ModuleRole,
    OutputForm,
    ReliabilityTier,
    UncertaintyKind,
)
from organism_sdk.health import HealthReport
from organism_sdk.inputs import PerceptionInput
from organism_sdk.justification import Emission
from organism_sdk.module import OrganismModule
from _common.contract_factory import make_contract

MODULE_ID = "physical_research"
MODULE_VERSION = "1.0.0"
FMT = "typed-json:phys-twin/v1"


@dataclass
class DigitalTwinTelemetry:
    latency_ms: float = 50.0
    reset_cost_j: float = 1.0
    plasticity: float = 0.1
    observability: float = 0.4
    last_sample_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "latency_ms": self.latency_ms,
            "reset_cost_j": self.reset_cost_j,
            "plasticity": self.plasticity,
            "observability": self.observability,
            "last_sample_at": self.last_sample_at,
            "research_sim": True,
        }


class PhysicalResearchModule(OrganismModule):
    """Exploration-only physical/molecular digital twin — never actuates."""

    def __init__(self) -> None:
        self.twin = DigitalTwinTelemetry()
        self._status = "HEALTHY"
        self._score = 1.0
        self._hypothesis_count = 0

    def declare_contract(self):
        return make_contract(
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
            write_tags=("physical", "exploration"),
            failure_name="physical_unobservable",
        )

    def health(self) -> HealthReport:
        return HealthReport(module_id=MODULE_ID, status=self._status, score=self._score)

    def sample_twin(self) -> dict[str, Any]:
        self.twin.last_sample_at = datetime.now(timezone.utc).isoformat()
        return self.twin.as_dict()

    def handle(self, input: PerceptionInput) -> Emission:
        if input.task_descriptor.form == "control_actuation":
            # Hard refuse control path
            body = json.dumps(
                {"refused": True, "reason": "physical_never_control_path", "research_sim": True}
            ).encode()
            return Emission(
                action_class="hold",
                payload=body,
                metadata={"module_id": MODULE_ID, "may_actuate": "False"},
            )
        self._hypothesis_count += 1
        twin = self.sample_twin()
        body = json.dumps(
            {
                "hypothesis_id": hashlib.sha256(
                    f"{self._hypothesis_count}:{input.task_descriptor.task_id}".encode()
                ).hexdigest()[:12],
                "twin": twin,
                "exploration_only": True,
            },
            sort_keys=True,
        ).encode()
        return Emission(
            action_class="exploration",
            payload=body,
            metadata={"module_id": MODULE_ID, "research_sim": "True"},
        )
