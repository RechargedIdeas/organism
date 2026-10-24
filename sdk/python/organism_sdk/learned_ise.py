"""Artifact G — Learned ISE / RL-DCA thin stub with promotion gate hooks.

T0 InteroceptiveStateEstimator remains the control-path estimator until a
learned successor passes shadow-validate + promotion gates. This module is
updateable for offline / EXPLORATION training only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from organism_sdk.interoceptive import HealthVector, InteroceptiveState, InteroceptiveStateEstimator, viability_f


@dataclass
class PromotionGate:
    """Hooks that must all pass before learned ISE may replace T0 on control path."""

    shadow_validated: bool = False
    calibration_ece_ok: bool = False
    cross_check_agree_rate: float = 0.0
    min_agree_rate: float = 0.95
    promoted: bool = False

    def ready(self) -> bool:
        return (
            self.shadow_validated
            and self.calibration_ece_ok
            and self.cross_check_agree_rate >= self.min_agree_rate
            and not self.promoted  # ready means eligible, not yet promoted
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "shadow_validated": self.shadow_validated,
            "calibration_ece_ok": self.calibration_ece_ok,
            "cross_check_agree_rate": self.cross_check_agree_rate,
            "min_agree_rate": self.min_agree_rate,
            "promoted": self.promoted,
            "ready": self.ready(),
        }


@dataclass
class RLDCAWeights:
    """Tiny online-updateable weights for Danger/PAMP/Safe signal refinement (stub)."""

    pamp_bias: float = 0.0
    danger_bias: float = 0.0
    safe_bias: float = 0.0
    updates: int = 0

    def update(self, label: str, *, lr: float = 0.05) -> None:
        self.updates += 1
        if label == "PAMP":
            self.pamp_bias = min(1.0, self.pamp_bias + lr)
        elif label == "DANGER":
            self.danger_bias = min(1.0, self.danger_bias + lr)
        elif label == "SAFE":
            self.safe_bias = min(1.0, self.safe_bias + lr)


class LearnedISE:
    """Updateable interoceptive predictor. Control-path use requires promotion."""

    def __init__(
        self,
        *,
        baseline: InteroceptiveStateEstimator | None = None,
        model_version: str = "0.2.0-learned-stub",
    ) -> None:
        self.baseline = baseline or InteroceptiveStateEstimator()
        self.model_version = model_version
        self.gate = PromotionGate()
        self.weights = RLDCAWeights()
        self._residual: list[float] = []
        self._control_path_active = False

    @property
    def control_path_active(self) -> bool:
        return self._control_path_active

    def update(self, h: HealthVector, observed_viability: float, *, lr: float = 0.1) -> float:
        """Offline / EXPLORATION residual update. Does not enable control path."""
        pred = viability_f(h)
        err = observed_viability - pred
        self._residual.append(err)
        self._residual = self._residual[-128:]
        # RL-DCA-style label nudge from residual magnitude
        if abs(err) > 0.2:
            self.weights.update("DANGER", lr=lr * 0.5)
        elif abs(err) < 0.05:
            self.weights.update("SAFE", lr=lr * 0.5)
        return err

    def estimate(self, h: HealthVector, *, for_control: bool = False) -> InteroceptiveState:
        if for_control and not self._control_path_active:
            raise PermissionError("learned ISE not promoted; T0 baseline required on control path")
        st = self.baseline.estimate(h)
        # Apply residual correction only when allowed (exploration or promoted)
        if self._residual and (not for_control or self._control_path_active):
            bias = sum(self._residual) / len(self._residual)
            adj = max(0.0, min(1.0, st.viability_score + 0.5 * bias))
            st.viability_score = adj
            st.model_version = self.model_version
        return st

    def record_shadow_validate(self, *, pass_rate: float, ece_ok: bool) -> PromotionGate:
        self.gate.shadow_validated = pass_rate >= 0.9
        self.gate.calibration_ece_ok = ece_ok
        self.gate.cross_check_agree_rate = pass_rate
        return self.gate

    def promote(self) -> bool:
        if not (
            self.gate.shadow_validated
            and self.gate.calibration_ece_ok
            and self.gate.cross_check_agree_rate >= self.gate.min_agree_rate
        ):
            return False
        self.gate.promoted = True
        self._control_path_active = True
        return True

    def demote(self) -> None:
        self.gate.promoted = False
        self._control_path_active = False
