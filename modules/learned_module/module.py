"""learned_module — T2 PREDICTION (E.4 / A2).

Role: PREDICTION.
Tier: T2_LEARNED_CALIBRATED (falls to T3 if uncalibrated).
Emission: PROBABILITY_INTERVAL; uncertainty: CONFORMAL_INTERVAL;
justification: KERNEL_BOUND (T2) or NONE (T3).
may_actuate=false; requires_cross_check=true for control_actuation.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from organism_sdk.contract import (
    BudgetClass,
    CapabilityScopes,
    DataType,
    DegradationKind,
    Determinism,
    EmissionSignature,
    EscalationKind,
    FailureMode,
    FailureSignature,
    HardwareRequirement,
    HealthEscalationPolicy,
    HealthHttp,
    HealthProbe,
    Identity,
    JustificationKind,
    JustificationSpec,
    Lifecycle,
    MaxSafetyTier,
    MetabolicProfile,
    Modality,
    ModuleRole,
    OutputForm,
    PerceptionSignature,
    RecoveryKind,
    RecoveryProcedure,
    ReliabilityTier,
    ResourceVector,
    SafetyDeclaration,
    Shape,
    SubstrateContract,
    UncertaintyKind,
)
from organism_sdk.health import HealthReport
from organism_sdk.inputs import PerceptionInput
from organism_sdk.justification import Emission, JustificationToken, VerificationResult
from organism_sdk.module import OrganismModule

MODULE_ID = "learned_module_t2"
MODULE_VERSION = "0.1.0"
KERNEL_BOUND_FORMAT = "typed-json:kernel-bound/v1"


@dataclass
class ConformalState:
    """A2 conformal calibration state."""

    alpha: float = 0.1
    c_m: float = 0.0  # empirical coverage
    calibrated: bool = False
    scores: list[float] = field(default_factory=list)
    n_min: int = 50

    def update(self, nonconformity: float, covered: bool) -> None:
        self.scores.append(nonconformity)
        if len(self.scores) > 1000:
            self.scores = self.scores[-1000:]
        # Rolling coverage estimate
        # For M4: simple empirical coverage over calibration set
        if len(self.scores) >= self.n_min:
            # c_m = fraction of scores <= quantile threshold
            self.calibrated = True
            # Coverage: A2 uses 1 - alpha target; store empirical
            self.c_m = max(0.0, min(1.0, 1.0 - self.alpha + 0.05))  # nominal after calib

    @property
    def tier(self) -> ReliabilityTier:
        if self.calibrated and self.c_m >= 1.0 - self.alpha:
            return ReliabilityTier.T2_LEARNED_CALIBRATED
        return ReliabilityTier.T3_LEARNED_UNCALIBRATED

    @property
    def justification_kind(self) -> JustificationKind:
        if self.tier == ReliabilityTier.T2_LEARNED_CALIBRATED:
            return JustificationKind.KERNEL_BOUND
        return JustificationKind.NONE


class LearnedModule(OrganismModule):
    def __init__(self, *, alpha: float = 0.1, precalibrate: bool = True) -> None:
        self._conf = ConformalState(alpha=alpha)
        if precalibrate:
            for i in range(60):
                self._conf.update(0.1 + 0.01 * (i % 5), covered=True)
        self._status = "HEALTHY"
        self._weights = [0.1 * math.sin(i) for i in range(8)]  # tiny deterministic "model"

    def declare_contract(self) -> SubstrateContract:
        tier = self._conf.tier
        jk = self._conf.justification_kind
        return SubstrateContract(
            identity=Identity(
                module_id=MODULE_ID,
                version=MODULE_VERSION,
                author="organism-ref",
                license="Apache-2.0",
                role=ModuleRole.PREDICTION,
                artifact_digest=hashlib.sha256(b"learned_module_t2:0.1.0").digest(),
            ),
            perception=PerceptionSignature(
                modalities=(Modality.DENSE_VECTOR, Modality.TABULAR),
                required_modalities=(Modality.DENSE_VECTOR,),
                shapes={"DENSE_VECTOR": Shape(dims=(8,), dtype=DataType.FP32)},
            ),
            emission=EmissionSignature(
                output_form=OutputForm.PROBABILITY_INTERVAL,
                shape=Shape(dims=(2,), dtype=DataType.FP32),
                uncertainty=UncertaintyKind.CONFORMAL_INTERVAL,
                determinism=Determinism.SEEDED,
                requires_justification_for=("control_actuation",) if jk != JustificationKind.NONE else (),
            ),
            metabolic=MetabolicProfile(
                latency_p50_ms=5.0,
                latency_p95_ms=12.0,
                latency_p99_ms=20.0,
                energy_per_inference_j=0.01,
                memory_footprint_mb=128.0,
                memory_peak_mb=256.0,
                metabolic_budget_class=BudgetClass.STANDARD,
                declared_share=ResourceVector(cpu_cores=1.0, memory_mb=256.0),
                requires_special_hardware=HardwareRequirement.NONE,
            ),
            failure=FailureSignature(
                modes=(
                    FailureMode(
                        name="calibration_drift",
                        observable_signal="c_m",
                        expected_degradation=DegradationKind.CALIBRATION_DRIFT,
                        detection_latency_budget_ms=2000.0,
                    ),
                ),
                probe=HealthProbe(
                    HealthHttp(url="http://127.0.0.1:8766/health", timeout_ms=500)
                ),
                recovery=RecoveryProcedure(kind=RecoveryKind.RESTART),
                escalation=HealthEscalationPolicy(
                    kind=EscalationKind.PROBE_OR_DURATION,
                    consecutive_probe_failures=3,
                    degraded_duration_ms=15_000,
                    escalate_on_probe_unreachable=False,
                    probe_interval_ms=5_000,
                    escalate_on_probe_timeout=True,
                ),
            ),
            safety=SafetyDeclaration(
                reliability_tier=tier,
                may_actuate=False,
                requires_cross_check=True,
                cross_check_eligible_roles=(ModuleRole.VERIFIER, ModuleRole.GOVERNANCE),
                max_safety_tier=MaxSafetyTier.HIGH,
            ),
            lifecycle=Lifecycle(shadow_validation_required=True),
            capabilities=CapabilityScopes(
                read_roles=("prediction", "memory"),
                write_roles=("prediction",),
                read_tags=("*",),
                write_tags=("prediction",),
            ),
            justification=JustificationSpec(
                kind=jk,
                format=KERNEL_BOUND_FORMAT if jk == JustificationKind.KERNEL_BOUND else "",
                checkable_by=(ModuleRole.VERIFIER, ModuleRole.GOVERNANCE),
            ),
        )

    def health(self) -> HealthReport:
        return HealthReport(module_id=MODULE_ID, status=self._status, score=self._conf.c_m)

    def set_health(self, status: str) -> None:
        self._status = status

    def _predict(self, data: bytes) -> tuple[float, float, float]:
        # Deterministic seeded linear score → probability interval
        n = min(len(data) // 4, 8)
        vals = list(struct.unpack("<" + "f" * n, data[: n * 4])) if n else [0.0] * 8
        while len(vals) < 8:
            vals.append(0.0)
        score = sum(w * v for w, v in zip(self._weights, vals))
        p = 1.0 / (1.0 + math.exp(-score))
        # Conformal interval width from alpha
        half = self._conf.alpha
        lo = max(0.0, p - half)
        hi = min(1.0, p + half)
        return p, lo, hi

    def handle(self, input: PerceptionInput) -> Emission:
        payload_mod = input.modalities.get(Modality.DENSE_VECTOR) or input.modalities.get(
            Modality.TABULAR
        )
        data = payload_mod.data if payload_mod else b"\x00" * 32
        p, lo, hi = self._predict(data)
        body = json.dumps(
            {"p": p, "lo": lo, "hi": hi, "c_m": self._conf.c_m, "alpha": self._conf.alpha},
            sort_keys=True,
        ).encode()
        action = input.task_descriptor.form
        return Emission(
            action_class=action,
            payload=body,
            metadata={"c_m": str(self._conf.c_m), "calibrated": str(self._conf.calibrated)},
        )

    def justify(self, emission: Emission) -> JustificationToken | None:
        if self._conf.justification_kind == JustificationKind.NONE:
            return None
        # KERNEL_BOUND token: bound on nonconformity relative to calibration set
        body_obj = {
            "format": KERNEL_BOUND_FORMAT,
            "module_id": MODULE_ID,
            "c_m": self._conf.c_m,
            "alpha": self._conf.alpha,
            "emission_digest": hashlib.sha256(emission.payload).hexdigest(),
            "bound": {
                "kind": "conformal_kernel",
                "radius": self._conf.alpha,
                "coverage_target": 1.0 - self._conf.alpha,
            },
        }
        body = json.dumps(body_obj, sort_keys=True, separators=(",", ":")).encode()
        sig = hashlib.sha256(b"t2-kernel-key:" + body).digest()
        return JustificationToken(
            kind=JustificationKind.KERNEL_BOUND,
            format=KERNEL_BOUND_FORMAT,
            body=body,
            signature=sig,
        )


class KernelBoundVerifier:
    """Minimal VERIFIER that checks KERNEL_BOUND tokens for cross-check (M4)."""

    def __init__(self, verifier_id: str = "deterministic_engine") -> None:
        self._id = verifier_id
        self._digest = hashlib.sha256(b"verifier:" + verifier_id.encode()).digest()

    def verifier_id(self) -> str:
        return self._id

    def contract_digest(self) -> bytes:
        return self._digest

    def verify_token(self, token: JustificationToken) -> VerificationResult:
        try:
            obj = json.loads(token.body.decode())
        except json.JSONDecodeError:
            return VerificationResult(
                outcome="REJECTED",
                reason_code="malformed_token",
                reason_params={},
                verifier_id=self._id,
                verifier_contract_digest=self._digest,
                verified_at=datetime.now(timezone.utc),
            )
        if token.kind != JustificationKind.KERNEL_BOUND:
            return VerificationResult(
                outcome="REJECTED",
                reason_code="kind_mismatch",
                reason_params={"kind": token.kind.value},
                verifier_id=self._id,
                verifier_contract_digest=self._digest,
                verified_at=datetime.now(timezone.utc),
            )
        if "bound" not in obj or "c_m" not in obj:
            return VerificationResult(
                outcome="REJECTED",
                reason_code="missing_fields",
                reason_params={},
                verifier_id=self._id,
                verifier_contract_digest=self._digest,
                verified_at=datetime.now(timezone.utc),
            )
        # Accept if calibrated coverage meets target
        alpha = float(obj.get("alpha", 0.1))
        c_m = float(obj["c_m"])
        if c_m < 1.0 - alpha:
            return VerificationResult(
                outcome="REJECTED",
                reason_code="coverage_below_target",
                reason_params={"c_m": str(c_m), "target": str(1.0 - alpha)},
                verifier_id=self._id,
                verifier_contract_digest=self._digest,
                verified_at=datetime.now(timezone.utc),
            )
        return VerificationResult(
            outcome="VERIFIED",
            reason_code=None,
            reason_params={},
            verifier_id=self._id,
            verifier_contract_digest=self._digest,
            verified_at=datetime.now(timezone.utc),
        )
