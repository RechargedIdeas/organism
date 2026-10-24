"""Artifact G / v0.3-M1 — Learned ISE with online RL-DCA-style prediction.

T0 InteroceptiveStateEstimator remains the control-path estimator until a
learned successor passes shadow-validate + promotion gates. Online updates
run in EXPLORATION / shadow only; prediction error can drive allostatic and
hormone *signals* without actuating until promoted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from organism_sdk.interoceptive import (
    HealthVector,
    InteroceptiveState,
    InteroceptiveStateEstimator,
    viability_f,
)


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
            and not self.promoted
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
    """Online Danger/PAMP/Safe refinement + linear predictive head (thin RL-DCA)."""

    pamp_bias: float = 0.0
    danger_bias: float = 0.0
    safe_bias: float = 0.0
    # Predictive head: w · features → viability residual vs T0
    w_thermal: float = 0.0
    w_latency: float = 0.0
    w_calibration: float = 0.0
    w_energy: float = 0.0
    w_det: float = 0.0
    w_module: float = 0.0
    bias: float = 0.0
    updates: int = 0

    def predict_residual(self, h: HealthVector) -> float:
        return (
            self.bias
            + self.w_thermal * (h.thermal - 1.0)
            + self.w_latency * (h.latency_ok - 1.0)
            + self.w_calibration * (h.calibration - 1.0)
            + self.w_energy * (h.energy - 1.0)
            + self.w_det * (h.det_ok - 1.0)
            + self.w_module * (h.module_health_min - 1.0)
        )

    def update_label(self, label: str, *, lr: float = 0.05) -> None:
        self.updates += 1
        if label == "PAMP":
            self.pamp_bias = min(1.0, self.pamp_bias + lr)
        elif label == "DANGER":
            self.danger_bias = min(1.0, self.danger_bias + lr)
        elif label == "SAFE":
            self.safe_bias = min(1.0, self.safe_bias + lr)

    def update_predictor(self, h: HealthVector, target_residual: float, *, lr: float = 0.1) -> float:
        """One SGD step on residual prediction; returns new prediction error."""
        pred = self.predict_residual(h)
        err = target_residual - pred
        self.bias += lr * err
        self.w_thermal += lr * err * (h.thermal - 1.0)
        self.w_latency += lr * err * (h.latency_ok - 1.0)
        self.w_calibration += lr * err * (h.calibration - 1.0)
        self.w_energy += lr * err * (h.energy - 1.0)
        self.w_det += lr * err * (h.det_ok - 1.0)
        self.w_module += lr * err * (h.module_health_min - 1.0)
        self.updates += 1
        return target_residual - self.predict_residual(h)


@dataclass
class AllostaticSignal:
    """Signal derived from prediction error — may nudge hormones, not actuate alone."""

    prediction_error: float
    stress_delta: float
    cortisol_nudge: float
    request_setpoint_adaptation: bool
    label: str  # SAFE | PAMP | DANGER

    def as_dict(self) -> dict[str, Any]:
        return {
            "prediction_error": self.prediction_error,
            "stress_delta": self.stress_delta,
            "cortisol_nudge": self.cortisol_nudge,
            "request_setpoint_adaptation": self.request_setpoint_adaptation,
            "label": self.label,
        }


@dataclass
class ShadowCompareResult:
    t0_viability: float
    learned_viability: float
    abs_delta: float
    agree: bool
    agree_threshold: float = 0.1


class LearnedISE:
    """Online predictive interoceptive model. Control-path use requires promotion."""

    def __init__(
        self,
        *,
        baseline: InteroceptiveStateEstimator | None = None,
        model_version: str = "0.3.0-learned-ise",
        agree_threshold: float = 0.1,
    ) -> None:
        self.baseline = baseline or InteroceptiveStateEstimator()
        self.model_version = model_version
        self.gate = PromotionGate()
        self.weights = RLDCAWeights()
        self._residual: list[float] = []
        self._pred_errors: list[float] = []
        self._control_path_active = False
        self.agree_threshold = agree_threshold
        self.last_allostatic: AllostaticSignal | None = None
        self._shadow_agreements: list[bool] = []

    @property
    def control_path_active(self) -> bool:
        return self._control_path_active

    def predict_viability(self, h: HealthVector) -> float:
        t0 = viability_f(h)
        return max(0.0, min(1.0, t0 + self.weights.predict_residual(h)))

    def update(self, h: HealthVector, observed_viability: float, *, lr: float = 0.1) -> float:
        """Online EXPLORATION residual + RL-DCA label update. Does not enable control path."""
        t0 = viability_f(h)
        target_residual = observed_viability - t0
        pred_err = self.weights.update_predictor(h, target_residual, lr=lr)
        self._residual.append(target_residual)
        self._residual = self._residual[-128:]
        self._pred_errors.append(pred_err)
        self._pred_errors = self._pred_errors[-128:]
        abs_err = abs(pred_err)
        if abs_err > 0.2:
            self.weights.update_label("DANGER", lr=lr * 0.5)
            label = "DANGER"
        elif abs_err > 0.08:
            self.weights.update_label("PAMP", lr=lr * 0.5)
            label = "PAMP"
        else:
            self.weights.update_label("SAFE", lr=lr * 0.5)
            label = "SAFE"
        stress_delta = min(1.0, abs_err)
        cortisol_nudge = min(1.0, abs_err * (0.5 + self.weights.danger_bias))
        self.last_allostatic = AllostaticSignal(
            prediction_error=pred_err,
            stress_delta=stress_delta,
            cortisol_nudge=cortisol_nudge,
            request_setpoint_adaptation=abs_err > 0.15,
            label=label,
        )
        return pred_err

    def allostatic_from_prediction_error(self, h: HealthVector | None = None) -> AllostaticSignal:
        """Expose last (or recompute) allostatic signal for HormoneBus consumers."""
        if self.last_allostatic is not None and h is None:
            return self.last_allostatic
        if h is None:
            return AllostaticSignal(0.0, 0.0, 0.0, False, "SAFE")
        # Recompute without weight update
        t0 = viability_f(h)
        pred = self.predict_viability(h)
        err = pred - t0
        abs_err = abs(err)
        label = "DANGER" if abs_err > 0.2 else ("PAMP" if abs_err > 0.08 else "SAFE")
        sig = AllostaticSignal(
            prediction_error=err,
            stress_delta=min(1.0, abs_err),
            cortisol_nudge=min(1.0, abs_err * (0.5 + self.weights.danger_bias)),
            request_setpoint_adaptation=abs_err > 0.15,
            label=label,
        )
        self.last_allostatic = sig
        return sig

    def apply_hormone_nudge(self, bus: Any, *, dt_s: float = 1.0) -> Any:
        """Apply prediction-error stress to HormoneBus without claiming control actuation.

        Safe pre-promotion: only modulates declared hormone release inputs.
        """
        sig = self.last_allostatic or AllostaticSignal(0.0, 0.0, 0.0, False, "SAFE")
        return bus.compute_release(
            stress_load=sig.stress_delta,
            viability_score=max(0.0, 1.0 - abs(sig.prediction_error)),
            crisis_precursor_count=1.0 if sig.label == "DANGER" else 0.0,
            dt_s=dt_s,
            source="learned_ise_allostatic",
        )

    def estimate(self, h: HealthVector, *, for_control: bool = False) -> InteroceptiveState:
        if for_control and not self._control_path_active:
            raise PermissionError("learned ISE not promoted; T0 baseline required on control path")
        st = self.baseline.estimate(h)
        pred = self.predict_viability(h)
        if not for_control or self._control_path_active:
            st.viability_score = pred
            st.model_version = self.model_version
            if self.last_allostatic and self.last_allostatic.request_setpoint_adaptation:
                st.request_setpoint_adaptation = True
            if self.last_allostatic and self.last_allostatic.label == "DANGER":
                st.crisis_precursor = True
                st.stress_load = max(st.stress_load, self.last_allostatic.stress_delta)
        return st

    def shadow_compare(self, h: HealthVector) -> ShadowCompareResult:
        t0 = viability_f(h)
        learned = self.predict_viability(h)
        delta = abs(learned - t0)
        agree = delta <= self.agree_threshold
        self._shadow_agreements.append(agree)
        self._shadow_agreements = self._shadow_agreements[-256:]
        return ShadowCompareResult(
            t0_viability=t0,
            learned_viability=learned,
            abs_delta=delta,
            agree=agree,
            agree_threshold=self.agree_threshold,
        )

    def record_shadow_validate(self, *, pass_rate: float | None = None, ece_ok: bool) -> PromotionGate:
        if pass_rate is None:
            if self._shadow_agreements:
                pass_rate = sum(self._shadow_agreements) / len(self._shadow_agreements)
            else:
                pass_rate = 0.0
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
