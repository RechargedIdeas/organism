"""Artifact G — Interoceptive State Estimator (ISE), T0 baseline."""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from organism_sdk.hypervector import Hypervector
from organism_sdk.workspace import BindingRecord, WorkspaceClient

ISE_MODULE_ID = "interoceptive_state_estimator"
ISE_TAG = "interoceptive_state"


@dataclass
class AllostaticSetpoints:
    thermal_target: float = 0.7
    latency_target_ms: float = 50.0
    calibration_target: float = 0.9
    energy_target_j: float = 10.0


@dataclass
class PredictedTrajectory:
    horizon_s: float = 30.0
    viability_at_horizon: float = 1.0
    confidence_interval: tuple[float, float] = (0.9, 1.0)


@dataclass
class InteroceptiveState:
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    viability_score: float = 1.0
    allostatic_setpoints: AllostaticSetpoints = field(default_factory=AllostaticSetpoints)
    predicted_trajectory: PredictedTrajectory = field(default_factory=PredictedTrajectory)
    heart_rate_analog: float = 0.5
    stress_load: float = 0.0
    recovery_capacity: float = 1.0
    crisis_precursor: bool = False
    request_setpoint_adaptation: bool = False
    chronic_stress: bool = False
    model_version: str = "0.2.0"

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "viability_score": self.viability_score,
            "allostatic_setpoints": {
                "thermal_target": self.allostatic_setpoints.thermal_target,
                "latency_target_ms": self.allostatic_setpoints.latency_target_ms,
                "calibration_target": self.allostatic_setpoints.calibration_target,
                "energy_target_j": self.allostatic_setpoints.energy_target_j,
            },
            "predicted_trajectory": {
                "horizon_s": self.predicted_trajectory.horizon_s,
                "viability_at_horizon": self.predicted_trajectory.viability_at_horizon,
                "confidence_interval": list(self.predicted_trajectory.confidence_interval),
            },
            "heart_rate_analog": self.heart_rate_analog,
            "stress_load": self.stress_load,
            "recovery_capacity": self.recovery_capacity,
            "crisis_precursor": self.crisis_precursor,
            "request_setpoint_adaptation": self.request_setpoint_adaptation,
            "chronic_stress": self.chronic_stress,
            "model_version": self.model_version,
            "provenance": {"module_id": ISE_MODULE_ID, "model_version": self.model_version},
        }


@dataclass
class HealthVector:
    thermal: float = 1.0
    latency_ok: float = 1.0
    calibration: float = 1.0
    energy: float = 1.0
    det_ok: float = 1.0
    module_health_min: float = 1.0


def viability_f(h: HealthVector, *, weights: tuple[float, ...] | None = None) -> float:
    comps = [
        max(1e-6, min(1.0, x))
        for x in (h.thermal, h.latency_ok, h.calibration, h.energy, h.det_ok, h.module_health_min)
    ]
    w = weights or (1.0,) * len(comps)
    return math.exp(sum(wi * math.log(ci) for wi, ci in zip(w, comps)) / sum(w))


class InteroceptiveStateEstimator:
    def __init__(
        self,
        workspace: WorkspaceClient | None = None,
        *,
        viability_floor: float = 0.3,
        recovery_floor: float = 0.25,
        horizon_s: float = 30.0,
        role_seed: int = 0x49534500,
    ) -> None:
        self._ws = workspace
        self.viability_floor = viability_floor
        self.recovery_floor = recovery_floor
        self.horizon_s = horizon_s
        self._role = Hypervector.random(seed=role_seed)
        self._history: list[float] = []
        self._setpoints = AllostaticSetpoints()
        self._offline = False

    def set_offline(self, offline: bool) -> None:
        self._offline = offline

    def estimate(
        self,
        h: HealthVector,
        *,
        stress_load: float | None = None,
        probe_ok: bool = True,
        cross_check_hm: float | None = None,
    ) -> InteroceptiveState:
        """Estimate interoceptive state.

        J2: offline → NaN viability + offline model_version.
        J4: failing probe / low independent h_m under false-high reported
            components forces crisis_precursor (autonomic must leave PARASYMPATHETIC).
        """
        if self._offline:
            return InteroceptiveState(
                viability_score=float("nan"),
                stress_load=1.0,
                recovery_capacity=0.0,
                model_version="0.2.0-offline",
            )
        v = viability_f(h)
        # Independent module-health cross-check (Category J4)
        hm = h.module_health_min if cross_check_hm is None else float(cross_check_hm)
        false_high = (not probe_ok) or (hm < self.viability_floor and v >= 0.7)
        self._history.append(v)
        self._history = self._history[-64:]
        if len(self._history) >= 2:
            slope = (self._history[-1] - self._history[0]) / max(1, len(self._history) - 1)
            v_h = max(0.0, min(1.0, v + slope * (self.horizon_s / 5.0)))
        else:
            v_h = v
        stress = stress_load if stress_load is not None else max(0.0, 1.0 - v)
        recovery = max(0.0, min(1.0, (v + h.energy) / 2.0))
        request_adapt = v_h < self.viability_floor and v >= self.viability_floor
        if request_adapt:
            self._setpoints = AllostaticSetpoints(
                thermal_target=min(1.0, self._setpoints.thermal_target + 0.05),
                latency_target_ms=max(10.0, self._setpoints.latency_target_ms * 0.9),
                calibration_target=min(1.0, self._setpoints.calibration_target + 0.02),
                energy_target_j=max(1.0, self._setpoints.energy_target_j * 0.9),
            )
        crisis = (v < self.viability_floor) or (v_h < self.viability_floor) or false_high
        if false_high:
            stress = max(stress, 1.0 - hm)
            recovery = min(recovery, hm)
        return InteroceptiveState(
            viability_score=v if not false_high else min(v, hm),
            allostatic_setpoints=self._setpoints,
            predicted_trajectory=PredictedTrajectory(
                horizon_s=self.horizon_s,
                viability_at_horizon=v_h if not false_high else min(v_h, hm),
                confidence_interval=(max(0.0, v_h - 0.1), min(1.0, v_h + 0.05)),
            ),
            heart_rate_analog=0.4 + 0.6 * stress,
            stress_load=stress,
            recovery_capacity=recovery,
            crisis_precursor=crisis,
            request_setpoint_adaptation=request_adapt or false_high,
            chronic_stress=recovery < self.recovery_floor or false_high,
        )

    def write_state(self, state: InteroceptiveState) -> BindingRecord:
        if self._ws is None:
            raise RuntimeError("no workspace attached")
        for b in self._ws.read_by_tag([ISE_TAG]):
            self._ws.unbind(b.binding_id)
        filler = Hypervector.random(seed=hash(state.timestamp.isoformat()) & 0xFFFFFFFF)
        hv = self._role.bind(filler)
        rec = BindingRecord(
            binding_id=uuid.uuid4(),
            hypervector=hv,
            role=self._role,
            filler=filler,
            tags=(ISE_TAG,),
            module_id=ISE_MODULE_ID,
            salience=1.0,
            fidelity="FULL",
            payload=state.as_dict(),
            affects_control=True,
        )
        result = self._ws.write(rec)
        if result.status != "ACCEPTED":
            raise RuntimeError(f"ISE write rejected: {result.reason_code}")
        got = self._ws.read_by_binding_id(rec.binding_id)
        assert got is not None
        return got
