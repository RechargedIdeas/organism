"""energy_hopfield — T1 SOLVER: modern Hopfield / energy minimization."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Sequence

from organism_sdk.contract import (
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

MODULE_ID = "energy_hopfield"
MODULE_VERSION = "1.0.0"
FMT = "typed-json:energy-cert/v1"

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


class EnergyHopfieldModule(OrganismModule):
    def __init__(self, *, dim: int = 8, beta: float = 2.0, steps: int = 20) -> None:
        self.dim = dim
        self.beta = beta
        self.steps = steps
        self.W = [[0.0] * dim for _ in range(dim)]
        for i in range(dim):
            for j in range(i + 1, dim):
                v = math.sin((i + 1) * (j + 3) * 0.37) * 0.4
                self.W[i][j] = self.W[j][i] = v
        self.patterns: list[list[float]] = []
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
            output_form=OutputForm.ASSIGNMENT_CERTIFICATE,
            uncertainty=UncertaintyKind.ENERGY_LANDSCAPE,
            determinism=Determinism.DETERMINISTIC,
            justification_kind=JustificationKind.ENERGY_CERT,
            justification_format=FMT,
            required_fields=("energy.value", "energy.converged"),
            requires_justification_for=("control_actuation", "assignment"),
            write_tags=("energy", "memory"),
            failure_name="energy_divergence",
        )

    def health(self) -> HealthReport:
        return HealthReport(module_id=MODULE_ID, status=self._status, score=self._score)

    def store_pattern(self, pattern: Sequence[float]) -> None:
        p = [1.0 if x >= 0 else -1.0 for x in pattern[: self.dim]]
        while len(p) < self.dim:
            p.append(-1.0)
        self.patterns.append(p)
        for i in range(self.dim):
            for j in range(self.dim):
                if i == j:
                    continue
                self.W[i][j] += 0.1 * p[i] * p[j]

    def energy(self, x: Sequence[float]) -> float:
        e = 0.0
        for i in range(self.dim):
            for j in range(self.dim):
                e -= 0.5 * x[i] * self.W[i][j] * x[j]
        return e

    def minimize(self, x0: Sequence[float]) -> tuple[list[float], float, bool]:
        x = list(x0[: self.dim]) + [0.0] * max(0, self.dim - len(x0))
        prev = self.energy(x)
        converged = False
        for _ in range(self.steps):
            grad = [0.0] * self.dim
            for i in range(self.dim):
                grad[i] = -sum(self.W[i][j] * x[j] for j in range(self.dim))
            x = [math.tanh(self.beta * (x[i] - 0.1 * grad[i])) for i in range(self.dim)]
            e = self.energy(x)
            if abs(e - prev) < 1e-6:
                converged = True
                break
            prev = e
        return x, prev, converged

    def handle(self, input: PerceptionInput) -> Emission:
        vec = _vector_from_input(input, self.dim)
        # map 0..1 to -1..1
        x0 = [v * 2 - 1 for v in vec]
        assignment, e, ok = self.minimize(x0)
        body = json.dumps(
            {"assignment": assignment, "energy": e, "converged": ok, "n_patterns": len(self.patterns)},
            sort_keys=True,
        ).encode()
        return Emission(
            action_class="assignment" if input.task_descriptor.form != "control_actuation" else "control_actuation",
            payload=body,
            metadata={"module_id": MODULE_ID, "beta": str(self.beta)},
        )

    def justify(self, emission: Emission) -> JustificationToken | None:
        try:
            p = json.loads(emission.payload.decode())
        except json.JSONDecodeError:
            p = {}
        body_obj = {
            "format": FMT,
            "energy.value": p.get("energy"),
            "energy.converged": p.get("converged"),
            "emission_digest": hashlib.sha256(emission.payload).hexdigest(),
        }
        body = json.dumps(body_obj, sort_keys=True, separators=(",", ":")).encode()
        return JustificationToken(
            kind=JustificationKind.ENERGY_CERT,
            format=FMT,
            body=body,
            signature=hashlib.sha256(b"energy-key:" + body).digest(),
        )
