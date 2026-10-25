"""HAL facade for bio-digital substrates — RESEARCH_SIM by default.

Mirrors Hybrid SensorInterface / ActuatorInterface without importing PySide6
or requiring real GPIO. When BIO_DIGITAL_HYBRID_ROOT resolves, wraps live
Hybrid SimulatedSensorSubsystem / SimulatedGalvanicActuator. Voltage limits
enforced; breaches raise.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from bio_digital.limits import BioLimits
from bio_digital.vendor_loader import load_hybrid

RUNTIME_RESEARCH_SIM = "RESEARCH_SIM"
RUNTIME_PHYSICAL = "PHYSICAL"  # reserved; not enabled in software Organism

BackendKind = Literal["stub", "live"]


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
    """Simulated sensor + galvanic actuator with BioLimits clamps.

    backend="auto" (default) uses live Hybrid HAL when vendor_loader finds a
    checkout; otherwise Organism stubs. Explicit backend="stub"|"live" forces.
    """

    def __init__(
        self,
        limits: BioLimits,
        *,
        node_id: str = "bio",
        backend: BackendKind | Literal["auto"] = "auto",
    ) -> None:
        self.limits = limits
        self.node_id = node_id
        self._electrodes: dict[str, float] = {}
        self.runtime_id = RUNTIME_RESEARCH_SIM if research_sim_enabled() else RUNTIME_PHYSICAL
        self._live_sensors: Any = None
        self._live_actuators: Any = None
        self.backend: BackendKind = "stub"

        want_live = backend == "live" or (backend == "auto")
        if want_live and backend != "stub":
            bundle = load_hybrid()
            if bundle.is_live and bundle.SimulatedSensorSubsystem is not None:
                mid = (limits.min_temp_c + limits.max_temp_c) / 2.0
                self._live_sensors = bundle.SimulatedSensorSubsystem(
                    target_temp=mid,
                    target_hum=limits.min_humidity + 5.0,
                    target_co2=limits.co2_target_ppm,
                )
                self._live_actuators = bundle.SimulatedGalvanicActuator(
                    max_safe_voltage=limits.max_voltage
                )
                self.backend = "live"

        if self.backend == "stub":
            mid = (limits.min_temp_c + limits.max_temp_c) / 2.0
            self._temp = mid
            self._hum = limits.min_humidity + 5.0
            self._co2 = limits.co2_target_ppm
        else:
            # Mirror live sensor state into local fields for set_environment.
            env = self._live_sensors.read_telemetry()
            self._temp = float(env.temp_c)
            self._hum = float(env.humidity_pct)
            self._co2 = float(env.co2_ppm)

    def read_telemetry(self) -> EnvironmentState:
        if self.backend == "live" and self._live_sensors is not None:
            # Keep live sensors in sync with any set_environment mutations.
            self._live_sensors._current_temp = self._temp
            self._live_sensors._current_hum = self._hum
            self._live_sensors._current_co2 = self._co2
            raw = self._live_sensors.read_telemetry()
            temp = float(raw.temp_c)
            hum = float(raw.humidity_pct)
            co2 = float(raw.co2_ppm)
        else:
            temp, hum, co2 = self._temp, self._hum, self._co2
        healthy = (
            self.limits.min_temp_c <= temp <= self.limits.max_temp_c
            and hum >= self.limits.min_humidity
        )
        return EnvironmentState(
            temp_c=temp,
            humidity_pct=hum,
            co2_ppm=co2,
            is_healthy=healthy,
        )

    def set_environment(
        self,
        *,
        temp_c: float | None = None,
        humidity_pct: float | None = None,
        co2_ppm: float | None = None,
    ) -> None:
        if temp_c is not None:
            self._temp = float(temp_c)
        if humidity_pct is not None:
            self._hum = float(humidity_pct)
        if co2_ppm is not None:
            self._co2 = float(co2_ppm)
        if self.backend == "live" and self._live_sensors is not None:
            self._live_sensors._current_temp = self._temp
            self._live_sensors._current_hum = self._hum
            self._live_sensors._current_co2 = self._co2

    def apply_potential(self, electrode_id: str, voltage: float) -> None:
        if abs(voltage) > self.limits.max_voltage:
            raise ValueError(
                f"Hardware Trap: {voltage}V exceeds substrate limits of {self.limits.max_voltage}V"
            )
        if self.backend == "live" and self._live_actuators is not None:
            self._live_actuators.apply_potential(electrode_id, float(voltage))
            # Mirror electrode map for sample_twin
            self._electrodes[electrode_id] = float(
                self._live_actuators._electrodes.get(electrode_id, voltage)
            )
        else:
            self._electrodes[electrode_id] = float(voltage)

    def read_impedance(self, electrode_id: str) -> float:
        if self.backend == "live" and self._live_actuators is not None:
            return float(self._live_actuators.read_impedance(electrode_id))
        current_v = self._electrodes.get(electrode_id, 0.0)
        return 25000.0 if current_v > 1.0 else 150000.0

    def sample_twin(self) -> dict[str, Any]:
        env = self.read_telemetry()
        return {
            "node_id": self.node_id,
            "runtime_id": self.runtime_id,
            "research_sim": self.runtime_id == RUNTIME_RESEARCH_SIM,
            "backend": self.backend,
            "temp_c": env.temp_c,
            "humidity_pct": env.humidity_pct,
            "co2_ppm": env.co2_ppm,
            "is_healthy": env.is_healthy,
            "electrodes": dict(self._electrodes),
            "sampled_at": datetime.now(timezone.utc).isoformat(),
            "affects_control": False,
        }
