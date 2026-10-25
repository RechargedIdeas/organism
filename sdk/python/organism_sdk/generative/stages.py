"""Shared evolution stages + promote gate (Learned-ISE style)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvolutionStage(str, Enum):
    INTENT = "INTENT"
    DRAFT = "DRAFT"
    STATIC_OK = "STATIC_OK"
    CONTRACT_OK = "CONTRACT_OK"
    SANDBOXED = "SANDBOXED"
    SHADOW_SCORED = "SHADOW_SCORED"
    PROMOTED = "PROMOTED"
    DEMOTION = "DEMOTION"
    REJECTED = "REJECTED"


@dataclass
class PromoteGate:
    """All hooks must pass before generative output may land on control / live looks."""

    static_ok: bool = False
    contract_ok: bool = False
    sandbox_ok: bool = False
    shadow_validated: bool = False
    shadow_score: float = 0.0
    min_shadow_score: float = 0.9
    promoted: bool = False

    def ready(self) -> bool:
        return (
            self.static_ok
            and self.contract_ok
            and self.sandbox_ok
            and self.shadow_validated
            and self.shadow_score >= self.min_shadow_score
            and not self.promoted
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "static_ok": self.static_ok,
            "contract_ok": self.contract_ok,
            "sandbox_ok": self.sandbox_ok,
            "shadow_validated": self.shadow_validated,
            "shadow_score": self.shadow_score,
            "min_shadow_score": self.min_shadow_score,
            "promoted": self.promoted,
            "ready": self.ready(),
        }
