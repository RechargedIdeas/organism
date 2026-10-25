"""generative_organism — RESEARCH_TIER code/asset/skill evolution substrate (v1.10.0).

Exploration-only: may_actuate=False always. Promote gates live in
organism_sdk.generative pipelines; this module is the registry-facing wrapper.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from _common.contract_factory import make_contract
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

MODULE_ID = "generative_organism"
MODULE_VERSION = "1.10.0"
FMT = "typed-json:generative/v1"


class GenerativeOrganismModule(OrganismModule):
    """Registry wrapper for Organism generative evolution — never actuates."""

    def __init__(self) -> None:
        self._status = "HEALTHY"
        self._score = 1.0
        self._drafts = 0

    def declare_contract(self):
        return make_contract(
            module_id=MODULE_ID,
            version=MODULE_VERSION,
            role=ModuleRole.FEATURE_EXTRACTOR,
            tier=ReliabilityTier.T3_LEARNED_UNCALIBRATED,
            modalities=(Modality.DENSE_VECTOR, Modality.TEXT),
            required_modalities=(Modality.DENSE_VECTOR,),
            output_form=OutputForm.FEATURE_VECTOR,
            uncertainty=UncertaintyKind.ENSEMBLE_SPREAD,
            determinism=Determinism.SEEDED,
            justification_kind=JustificationKind.NONE,
            justification_format=FMT,
            required_fields=(),
            may_actuate=False,
            requires_cross_check=True,
            max_safety=MaxSafetyTier.RESEARCH,
            budget=BudgetClass.RESEARCH,
            hardware=HardwareRequirement.NONE,
            write_tags=("generative", "skill", "asset", "exploration"),
            failure_name="generative_gate_reject",
        )

    def health(self) -> HealthReport:
        return HealthReport(module_id=MODULE_ID, status=self._status, score=self._score)

    def handle(self, input: PerceptionInput) -> Emission:
        if input.task_descriptor.form == "control_actuation":
            body = json.dumps(
                {
                    "refused": True,
                    "reason": "generative_never_control_without_promote",
                    "research_tier": True,
                    "may_actuate": False,
                }
            ).encode()
            return Emission(
                action_class="hold",
                payload=body,
                metadata={"module_id": MODULE_ID, "may_actuate": "False"},
            )
        self._drafts += 1
        body = json.dumps(
            {
                "draft_seq": self._drafts,
                "task_id": input.task_descriptor.task_id,
                "exploration_only": True,
                "cpu_everywhere": True,
                "at": datetime.now(timezone.utc).isoformat(),
            },
            sort_keys=True,
        ).encode()
        return Emission(
            action_class="exploration",
            payload=body,
            metadata={"module_id": MODULE_ID, "research_tier": "True"},
        )

    def on_drain(self, deadline: datetime) -> None:
        return None
