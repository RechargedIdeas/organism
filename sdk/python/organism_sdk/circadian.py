"""Artifact J — CircadianClock + Kleiber metabolic scaling."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CircadianState:
    phase: float = 0.0
    sleep_pressure: float = 0.0
    in_rest: bool = False
    consolidation_preferred: bool = False
    exploration_scale: float = 1.0
    melatonin_baseline: float = 0.0
    cortisol_baseline: float = 0.2


class CircadianClock:
    def __init__(self, *, rest_start: float = 0.7, rest_end: float = 1.0, pressure_gain: float = 0.02, crisis_suppresses_rest: bool = True) -> None:
        self.rest_start = rest_start
        self.rest_end = rest_end
        self.pressure_gain = pressure_gain
        self.crisis_suppresses_rest = crisis_suppresses_rest
        self.phase = 0.0
        self.sleep_pressure = 0.0

    def advance(self, dt_phase: float = 0.05, *, sympathetic_load: float = 0.0, crisis: bool = False) -> CircadianState:
        self.phase = (self.phase + dt_phase) % 1.0
        self.sleep_pressure = min(1.0, self.sleep_pressure + self.pressure_gain * (1.0 + sympathetic_load))
        time_of_day_rest = self.rest_start <= self.phase < self.rest_end
        pressure_rest = self.sleep_pressure >= 0.8
        in_rest = time_of_day_rest or pressure_rest
        if crisis and self.crisis_suppresses_rest:
            in_rest = False
        if in_rest:
            self.sleep_pressure = max(0.0, self.sleep_pressure - 0.1)
        melatonin = 0.0 if crisis else (0.8 if in_rest else 0.05)
        return CircadianState(
            phase=self.phase,
            sleep_pressure=self.sleep_pressure,
            in_rest=in_rest,
            consolidation_preferred=in_rest and not crisis,
            exploration_scale=0.05 if in_rest else 1.0,
            melatonin_baseline=melatonin,
            cortisol_baseline=0.1 if in_rest else 0.25,
        )

    def apply_to_autonomic_params(self, params: dict[str, Any], state: CircadianState) -> dict[str, Any]:
        out = dict(params)
        out["exploration_budget"] = float(out.get("exploration_budget", 1.0)) * state.exploration_scale
        out["circadian_phase"] = state.phase
        out["circadian_in_rest"] = state.in_rest
        out["circadian_melatonin_baseline"] = state.melatonin_baseline
        return out


def kleiber_declared_share(functional_complexity: float, *, k: float = 1.0, beta: float = 0.75) -> float:
    if not 0.7 <= beta <= 0.8:
        raise ValueError("beta must be in [0.7, 0.8]")
    if functional_complexity < 0:
        raise ValueError("functional_complexity must be >= 0")
    return k * (functional_complexity ** beta)


def metabolic_inefficiency(measured_energy_j: float, predicted_share: float, *, margin: float = 1.5) -> bool:
    if predicted_share <= 0:
        return measured_energy_j > 0
    return measured_energy_j > predicted_share * margin
