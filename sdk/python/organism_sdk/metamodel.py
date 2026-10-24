"""Metamodel reproductive synthesizer — E.8 deferred for v0.2.

Reproductive path (synthesis → sandbox → shadow-validate → promote) stays
disabled. This module exists so CI can prove the path is not open.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class MetamodelDisabled(Exception):
    """Raised when reproductive synthesis is attempted in v0.2."""


@dataclass
class SynthesisRequest:
    spec: dict[str, Any]
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MetamodelTracker:
    """Tracker-only: records attempts; never synthesizes or promotes."""

    enabled: bool = False  # v0.2: always False unless corpus opens E.8
    attempts: list[dict[str, Any]] = field(default_factory=list)

    def synthesize(self, spec: dict[str, Any]) -> None:
        self.attempts.append(
            {
                "spec": spec,
                "at": datetime.now(timezone.utc).isoformat(),
                "accepted": False,
                "reason": "E.8_metamodel_reproductive_disabled",
            }
        )
        raise MetamodelDisabled(
            "Metamodel reproductive synthesizer is E.8 out of scope for v0.2"
        )

    def reproductive_path_enabled(self) -> bool:
        return False
