"""Wet-lab HAL — simulated loop by default; real GPIO open gated (v1.4)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from bio_digital.limits import BioLimits
from bio_digital.wetlab.safety import ActuationDenied, SafetyPolicy

DeviceStatus = Literal["sim", "device_missing", "opened", "refused"]


def gpio_env_enabled() -> bool:
    v = os.environ.get("ORGANISM_WETLAB_GPIO", "0").strip().lower()
    return v in {"1", "true", "yes", "on"}


@dataclass
class WetLabLoopResult:
    steps: int
    readings: list[dict[str, Any]] = field(default_factory=list)
    actuations_attempted: int = 0
    actuations_applied: int = 0
    actuations_denied: int = 0
    device_status: DeviceStatus = "sim"
    exploration_only: bool = True
    affects_control: bool = False


class WetLabHAL:
    """Sensor/actuator loop with BioLimits clamps + SafetyPolicy gate.

    Default policy denies actuation. Real device open requires
    ORGANISM_WETLAB_GPIO=1 AND certified policy; otherwise no-op / sim.
    """

    def __init__(
        self,
        limits: BioLimits,
        *,
        policy: SafetyPolicy | None = None,
        node_id: str = "wetlab",
        device_path: str | None = None,
    ) -> None:
        self.limits = limits
        self.policy = policy or SafetyPolicy.deny_all(max_voltage=limits.max_voltage)
        self.node_id = node_id
        self.device_path = device_path or os.environ.get("ORGANISM_WETLAB_DEVICE", "")
        mid = (limits.min_temp_c + limits.max_temp_c) / 2.0
        self._temp = mid
        self._hum = limits.min_humidity + 5.0
        self._co2 = limits.co2_target_ppm
        self._electrodes: dict[str, float] = {}
        self._device_handle: Any = None
        self.device_status: DeviceStatus = "sim"
        self.may_actuate_declared = False  # modules remain may_actuate=False

    def is_healthy(self) -> bool:
        return (
            self.limits.min_temp_c <= self._temp <= self.limits.max_temp_c
            and self._hum >= self.limits.min_humidity
        )

    def read_sensors(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "temp_c": self._temp,
            "humidity_pct": self._hum,
            "co2_ppm": self._co2,
            "is_healthy": self.is_healthy(),
            "electrodes": dict(self._electrodes),
            "device_status": self.device_status,
            "affects_control": False,
            "exploration_only": True,
            "sampled_at": datetime.now(timezone.utc).isoformat(),
        }

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

    def clamp_voltage(self, voltage: float) -> float:
        cap = min(self.limits.max_voltage, self.policy.max_voltage or self.limits.max_voltage)
        if cap <= 0:
            cap = self.limits.max_voltage
        if abs(voltage) > cap:
            raise ValueError(
                f"voltage clamp: {voltage}V exceeds max_voltage={cap}V "
                f"(limits={self.limits.max_voltage}, policy={self.policy.max_voltage})"
            )
        return float(voltage)

    def try_open_device(self) -> DeviceStatus:
        """Attempt real GPIO open. Default: refuse or device_missing."""
        allowed, reason = self.policy.may_actuate(
            gpio_env=gpio_env_enabled(), substrate_healthy=self.is_healthy()
        )
        if not allowed:
            self.device_status = "refused"
            return self.device_status
        # Certified + env: still no-op if no device node on this box
        path = self.device_path
        if not path or not os.path.exists(path):
            self.device_status = "device_missing"
            self._device_handle = None
            return self.device_status
        # Placeholder: we do not open arbitrary device files in software Organism.
        # A future HAL driver may set _device_handle here under certified policy.
        self.device_status = "opened"
        self._device_handle = {"path": path, "opened_at": datetime.now(timezone.utc).isoformat()}
        return self.device_status

    def apply_potential(self, electrode_id: str, voltage: float) -> None:
        v = self.clamp_voltage(voltage)
        allowed, reason = self.policy.may_actuate(
            gpio_env=gpio_env_enabled(), substrate_healthy=self.is_healthy()
        )
        if not allowed:
            raise ActuationDenied(f"wetlab actuation denied: {reason}")
        # Even when allowed, sim applies to in-memory map; real device only if opened
        self._electrodes[electrode_id] = v
        if self.device_status == "opened" and self._device_handle is not None:
            # No-op write placeholder — real driver would clock out voltage here
            self._device_handle["last"] = {"electrode": electrode_id, "voltage": v}

    def run_sim_loop(
        self,
        *,
        steps: int = 8,
        voltage: float = 0.1,
        electrode_id: str = "A0",
        attempt_actuate: bool = True,
    ) -> WetLabLoopResult:
        """Simulated sensor/actuator loop for tests (exploration-only)."""
        result = WetLabLoopResult(steps=steps, device_status=self.device_status)
        self.try_open_device()
        result.device_status = self.device_status
        for i in range(steps):
            # Mild environment drift inside limits
            self._temp = self.limits.min_temp_c + (self.limits.max_temp_c - self.limits.min_temp_c) * (
                0.4 + 0.2 * ((i % 5) / 5.0)
            )
            reading = self.read_sensors()
            result.readings.append(reading)
            if attempt_actuate:
                result.actuations_attempted += 1
                try:
                    self.apply_potential(electrode_id, voltage)
                    result.actuations_applied += 1
                except (ActuationDenied, ValueError):
                    result.actuations_denied += 1
        return result
