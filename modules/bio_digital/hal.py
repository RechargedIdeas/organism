"""HAL facade for bio-digital substrates — RESEARCH_SIM by default.

Mirrors Hybrid SensorInterface / ActuatorInterface without importing PySide6
or requiring real GPIO. Voltage limits enforced; breaches raise.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from bio_digital.limits import BioLimits

RUNTIME_RESEARCH_SIM = "RESEARCH_SIM"
RUNTIME_PHYSICAL = "PHYSICAL"  # reserved; not enabled in software Organism


def research_sim_enabled() -> bool:
    """True unless ORGANISM_BIO_DIGITAL_SIM explicitly disables sim.

    Default: RESEARCH_SIM on (software Organism has no wet-lab).
    Set ORGANISM_BIO_DIGITAL_SIM=0 to mark facade as unavailable physical.
    """
    v = os.environ.get("ORGANISM_BIO_DIGITAL_SIM", "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


@dataclass
class EnvironmentState:
    temp_c: float
    humidity_pct: float
    co2_ppm: float
    is_healthy: bool = True


class BioDigitalHAL:
    """Simulated sensor + galvanic actuator with BioLimits clamps."""

    def __init__(self, limits: BioLimits, *, node_id: str = "bio") -> None:
        self.limits = limits
        self.node_id = node_id
        mid = (limits.min_temp_c + limits.max_temp_c) / 2.0
        self._temp = mid
        self._hum = limits.min_humidity + 5.0
        self._co2 = limits.co2_target_ppm
        self._electrodes: dict[str, float] = {}
        self.runtime_id = RUNTIME_RESEARCH_SIM if research_sim_enabled() else RUNTIME_PHYSICAL

    def read_telemetry(self) -> EnvironmentState:
        healthy = (
            self.limits.min_temp_c <= self._temp <= self.limits.max_temp_c
            and self._hum >= self.limits.min_humidity
        )
        return EnvironmentState(
            temp_c=self._temp,
            humidity_pct=self._hum,
            co2_ppm=self._co2,
            is_healthy=healthy,
        )

    def set_environment(self, *, temp_c: float | None = None, humidity_pct: float | None = None, co2_ppm: float | None = None) -> None:
        if temp_c is not None:
            self._temp = float(temp_c)
        if humidity_pct is not None:
            self._hum = float(humidity_pct)
        if co2_ppm is not None:
            self._co2 = float(co2_ppm)

    def apply_potential(self, electrode_id: str, voltage: float) -> None:
        if abs(voltage) > self.limits.max_voltage:
            raise ValueError(
                f"Hardware Trap: {voltage}V exceeds substrate limits of {self.limits.max_voltage}V"
            )
        self._electrodes[electrode_id] = float(voltage)

    def read_impedance(self, electrode_id: str) -> float:
        current_v = self._electrodes.get(electrode_id, 0.0)
        return 25000.0 if current_v > 1.0 else 150000.0

    def sample_twin(self) -> dict[str, Any]:
        env = self.read_telemetry()
        return {
            "node_id": self.node_id,
            "runtime_id": self.runtime_id,
            "research_sim": self.runtime_id == RUNTIME_RESEARCH_SIM,
            "temp_c": env.temp_c,
            "humidity_pct": env.humidity_pct,
            "co2_ppm": env.co2_ppm,
            "is_healthy": env.is_healthy,
            "electrodes": dict(self._electrodes),
            "sampled_at": datetime.now(timezone.utc).isoformat(),
        }
