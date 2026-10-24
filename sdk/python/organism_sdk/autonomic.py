"""Artifact I — AutonomicController. Modulates router-exposed params only."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from organism_sdk.trace import AutonomicTraceEntry, TraceEmitter

AutonomicMode = Literal["PARASYMPATHETIC", "SYMPATHETIC", "CRISIS", "RECOVERY"]


@dataclass
class RouterExposedParams:
    preemption_class: str = "NORMAL"
    cross_check_frequency: float = 1.0
    exploration_budget: float = 1.0
    metabolic_multiplier: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "preemption_class": self.preemption_class,
            "cross_check_frequency": self.cross_check_frequency,
            "exploration_budget": self.exploration_budget,
            "metabolic_multiplier": self.metabolic_multiplier,
        }


def _params_for_mode(mode: AutonomicMode) -> RouterExposedParams:
    if mode == "PARASYMPATHETIC":
        return RouterExposedParams()
    if mode == "SYMPATHETIC":
        return RouterExposedParams("PREEMPT_RESEARCH", 1.5, 0.3, 0.8)
    if mode == "CRISIS":
        return RouterExposedParams("PREEMPT_NON_T0_T1", 2.0, 0.0, 0.5)
    return RouterExposedParams("NORMAL", 1.2, 0.4, 0.9)


@dataclass
class AutonomicConfig:
    sympathetic_viability: float = 0.6
    crisis_viability: float = 0.3
    recovery_viability: float = 0.8
    cortisol_sympathetic: float = 0.5
    t_down_s: float = 0.05
    t_up_s: float = 0.25
    t_recovery_dwell_s: float = 0.2


class AutonomicController:
    def __init__(
        self,
        *,
        trace: TraceEmitter | None = None,
        config: AutonomicConfig | None = None,
        clock: Any | None = None,
    ) -> None:
        self._trace = trace
        self.config = config or AutonomicConfig()
        self._clock = clock or (lambda: datetime.now(timezone.utc).timestamp())
        self._lock = threading.RLock()
        self.mode: AutonomicMode = "PARASYMPATHETIC"
        self.params = _params_for_mode(self.mode)
        self._armed_since: float | None = None
        self._pending_mode: AutonomicMode | None = None
        self.transitions: list[tuple[str, str, str, float]] = []
        self._select_module_attempts = 0

    def now(self) -> float:
        return float(self._clock())

    def select_module_for_task(self, *_a: Any, **_k: Any) -> None:
        self._select_module_attempts += 1
        raise PermissionError("AU-5: AutonomicController does not select modules")

    @property
    def select_module_attempts(self) -> int:
        return self._select_module_attempts

    def tick(
        self,
        *,
        viability: float,
        cortisol: float = 0.0,
        crisis_precursor: bool = False,
        pamp: bool = False,
        level: str = "L0",
    ) -> RouterExposedParams:
        with self._lock:
            desired = self._desired(viability=viability, cortisol=cortisol, crisis_precursor=crisis_precursor, pamp=pamp, level=level)
            t = self.now()
            if desired == self.mode:
                self._pending_mode = None
                self._armed_since = None
                return self.params
            recovering = desired == "RECOVERY" or (
                self.mode in ("CRISIS", "SYMPATHETIC", "RECOVERY") and desired == "PARASYMPATHETIC"
            )
            if desired in ("CRISIS", "SYMPATHETIC") and (crisis_precursor or pamp):
                return self._transition(desired, trigger="fast_path")
            if self._pending_mode != desired:
                self._pending_mode = desired
                self._armed_since = t
                return self.params
            assert self._armed_since is not None
            need = self.config.t_recovery_dwell_s if desired == "RECOVERY" else (
                self.config.t_up_s if recovering else self.config.t_down_s
            )
            if t - self._armed_since >= need:
                return self._transition(desired, trigger="recovery" if recovering else "stress")
            return self.params

    def _desired(self, *, viability: float, cortisol: float, crisis_precursor: bool, pamp: bool, level: str) -> AutonomicMode:
        if crisis_precursor or viability < self.config.crisis_viability or level in ("L3", "L4"):
            return "CRISIS"
        if pamp or cortisol >= self.config.cortisol_sympathetic or viability < self.config.sympathetic_viability:
            if self.mode == "CRISIS":
                return "RECOVERY" if viability >= self.config.recovery_viability else "CRISIS"
            return "SYMPATHETIC"
        if self.mode in ("CRISIS", "SYMPATHETIC", "RECOVERY"):
            if viability >= self.config.recovery_viability:
                return "PARASYMPATHETIC" if self.mode == "RECOVERY" else "RECOVERY"
            return "CRISIS" if self.mode == "CRISIS" else "SYMPATHETIC"
        return "PARASYMPATHETIC"

    def _transition(self, to_mode: AutonomicMode, *, trigger: str) -> RouterExposedParams:
        from_mode = self.mode
        self.mode = to_mode
        self.params = _params_for_mode(to_mode)
        self._pending_mode = None
        self._armed_since = None
        self.transitions.append((from_mode, to_mode, trigger, self.now()))
        if self._trace is not None:
            self._trace.emit_autonomic(
                AutonomicTraceEntry(
                    from_mode=from_mode,
                    to_mode=to_mode,
                    preemption_class=self.params.preemption_class,
                    cross_check_frequency=self.params.cross_check_frequency,
                    exploration_budget=self.params.exploration_budget,
                    trigger=trigger,
                )
            )
        return self.params

    def force_mode(self, mode: AutonomicMode, *, trigger: str = "test") -> RouterExposedParams:
        with self._lock:
            return self._transition(mode, trigger=trigger)
