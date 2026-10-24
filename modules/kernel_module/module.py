"""kernel_module — T1 SOLVER: RBF kernel fallback + ridge readout trainer hooks."""
from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass, field
from typing import Sequence

from organism_sdk.contract import (
    DegradationKind,
    Determinism,
    JustificationKind,
    Modality,
    ModuleRole,
    OutputForm,
    ReliabilityTier,
    UncertaintyKind,
)
from organism_sdk.health import HealthReport
from organism_sdk.inputs import PerceptionInput
from organism_sdk.justification import Emission, JustificationToken
from organism_sdk.module import OrganismModule
from _common.contract_factory import make_contract

MODULE_ID = "kernel_module"
MODULE_VERSION = "1.0.0"
KERNEL_BOUND_FORMAT = "typed-json:kernel-bound/v1"


@dataclass
class RidgeReadout:
    weights: list[float] = field(default_factory=list)
    bias: float = 0.0
    lambda_reg: float = 1e-2
    fitted: bool = False
    n_samples: int = 0

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> None:
        if not X or not y or len(X) != len(y):
            raise ValueError("fit requires matching X,y")
        d = len(X[0])
        xtx = [[0.0] * d for _ in range(d)]
        xty = [0.0] * d
        for row, yi in zip(X, y):
            for i in range(d):
                xty[i] += row[i] * yi
                for j in range(d):
                    xtx[i][j] += row[i] * row[j]
        for i in range(d):
            xtx[i][i] += self.lambda_reg
        a = [r[:] + [xty[i]] for i, r in enumerate(xtx)]
        n = d
        for col in range(n):
            pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
            a[col], a[pivot] = a[pivot], a[col]
            div = a[col][col] or 1e-12
            for j in range(col, n + 1):
                a[col][j] /= div
            for r in range(n):
                if r == col:
                    continue
                f = a[r][col]
                for j in range(col, n + 1):
                    a[r][j] -= f * a[col][j]
        self.weights = [a[i][n] for i in range(n)]
        means = [sum(row[i] for row in X) / len(X) for i in range(d)]
        self.bias = sum(y) / len(y) - sum(self.weights[i] * means[i] for i in range(d))
        self.fitted = True
        self.n_samples = len(y)

    def predict(self, x: Sequence[float]) -> float:
        if not self.fitted:
            return 0.0
        return self.bias + sum(w * xi for w, xi in zip(self.weights, x))


def rbf_kernel(a: Sequence[float], b: Sequence[float], gamma: float = 1.0) -> float:
    s = sum((x - y) ** 2 for x, y in zip(a, b))
    return math.exp(-gamma * s)



def _vector_from_input(inp: PerceptionInput, dim: int = 8) -> list[float]:
    import struct
    for mod in (Modality.DENSE_VECTOR, Modality.TABULAR, Modality.TEMPORAL_STREAM, Modality.WAVELET_COEFFS):
        p = inp.modalities.get(mod)
        if p is None:
            continue
        raw = p.data
        n = len(raw) // 4
        if n <= 0:
            continue
        vals = list(struct.unpack("<" + "f" * n, raw[: n * 4]))
        out = vals[:dim]
        while len(out) < dim:
            out.append(0.0)
        return out
    tid = inp.task_descriptor.task_id
    return [((ord(c) % 17) / 17.0) for c in (tid + "xxxxxxxx")[:dim]]


class KernelModule(OrganismModule):
    def __init__(self, *, gamma: float = 1.0, coreset: Sequence[Sequence[float]] | None = None) -> None:
        self.gamma = gamma
        self.coreset: list[list[float]] = [list(r) for r in (coreset or [[1.0] * 8])]
        self.readout = RidgeReadout()
        self._status = "HEALTHY"
        self._score = 1.0

    def declare_contract(self):
        return make_contract(
            module_id=MODULE_ID,
            version=MODULE_VERSION,
            role=ModuleRole.SOLVER,
            tier=ReliabilityTier.T1_CALIBRATED_NONLEARNED,
            modalities=(Modality.DENSE_VECTOR, Modality.TABULAR),
            required_modalities=(Modality.DENSE_VECTOR,),
            output_form=OutputForm.PROBABILITY_INTERVAL,
            uncertainty=UncertaintyKind.ENSEMBLE_SPREAD,
            determinism=Determinism.DETERMINISTIC,
            justification_kind=JustificationKind.KERNEL_BOUND,
            justification_format=KERNEL_BOUND_FORMAT,
            required_fields=("kernel.gamma", "kernel.coreset_size"),
            requires_justification_for=("control_actuation",),
            write_tags=("kernel", "memory"),
            failure_name="kernel_divergence",
            failure_kind=DegradationKind.SILENT_ACCURACY_LOSS,
        )

    def health(self) -> HealthReport:
        return HealthReport(module_id=MODULE_ID, status=self._status, score=self._score)

    def fit_readout(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> RidgeReadout:
        self.readout.fit(X, y)
        return self.readout

    def handle(self, input: PerceptionInput) -> Emission:
        vec = _vector_from_input(input, dim=8)
        sims = [rbf_kernel(vec, c, self.gamma) for c in self.coreset]
        score = sum(sims) / max(1, len(sims))
        if self.readout.fitted:
            score = 0.5 * score + 0.5 * max(0.0, min(1.0, self.readout.predict(vec)))
        lo, hi = max(0.0, score - 0.05), min(1.0, score + 0.05)
        body = json.dumps(
            {"interval": [lo, hi], "point": score, "sims": sims},
            sort_keys=True,
        ).encode()
        return Emission(
            action_class=input.task_descriptor.form,
            payload=body,
            metadata={
                "module_id": MODULE_ID,
                "gamma": str(self.gamma),
                "coreset_size": str(len(self.coreset)),
            },
        )

    def justify(self, emission: Emission) -> JustificationToken | None:
        body_obj = {
            "format": KERNEL_BOUND_FORMAT,
            "module_id": MODULE_ID,
            "kernel.gamma": self.gamma,
            "kernel.coreset_size": len(self.coreset),
            "kernel.readout_fitted": self.readout.fitted,
            "emission_digest": hashlib.sha256(emission.payload).hexdigest(),
        }
        body = json.dumps(body_obj, sort_keys=True, separators=(",", ":")).encode()
        return JustificationToken(
            kind=JustificationKind.KERNEL_BOUND,
            format=KERNEL_BOUND_FORMAT,
            body=body,
            signature=hashlib.sha256(b"kernel-key:" + body).digest(),
        )
