"""reservoir — T1 PREDICTION: fixed echo-state dynamics + ridge readout."""
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
from kernel_module.module import RidgeReadout

MODULE_ID = "reservoir"
MODULE_VERSION = "1.0.0"
FMT = "typed-json:reservoir-state/v1"

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


def _det_matrix(n: int, seed: int) -> list[list[float]]:
    W = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            v = math.sin((i + 1) * (j + 1) * (seed + 1) * 0.017) * 0.3
            if abs(v) < 0.05:
                v = 0.0
            W[i][j] = v
    row_sums = [sum(abs(x) for x in row) for row in W]
    scale = max(row_sums) or 1.0
    return [[x / scale * 0.9 for x in row] for row in W]


class ReservoirModule(OrganismModule):
    def __init__(self, *, size: int = 16, seed: int = 3, leak: float = 0.3) -> None:
        self.size = size
        self.seed = seed
        self.leak = leak
        self.W = _det_matrix(size, seed)
        self.Win = [
            [math.cos((i + 1) * (j + 1) * 0.11 + seed) * 0.5 for j in range(8)]
            for i in range(size)
        ]
        self.state = [0.0] * size
        self.readout = RidgeReadout(lambda_reg=1e-3)
        self._status = "HEALTHY"
        self._score = 1.0

    def declare_contract(self):
        return make_contract(
            module_id=MODULE_ID,
            version=MODULE_VERSION,
            role=ModuleRole.PREDICTION,
            tier=ReliabilityTier.T1_CALIBRATED_NONLEARNED,
            modalities=(Modality.TEMPORAL_STREAM, Modality.DENSE_VECTOR),
            required_modalities=(Modality.DENSE_VECTOR,),
            output_form=OutputForm.PROBABILITY_INTERVAL,
            uncertainty=UncertaintyKind.ENSEMBLE_SPREAD,
            determinism=Determinism.SEEDED,
            justification_kind=JustificationKind.KERNEL_BOUND,
            justification_format=FMT,
            required_fields=("reservoir.size", "reservoir.leak"),
            requires_justification_for=("control_actuation",),
            write_tags=("reservoir", "memory"),
            failure_name="reservoir_silence",
        )

    def health(self) -> HealthReport:
        return HealthReport(module_id=MODULE_ID, status=self._status, score=self._score)

    def step(self, u: Sequence[float]) -> list[float]:
        u8 = list(u[:8]) + [0.0] * max(0, 8 - len(u))
        pre = [0.0] * self.size
        for i in range(self.size):
            s = sum(self.Win[i][j] * u8[j] for j in range(8))
            s += sum(self.W[i][j] * self.state[j] for j in range(self.size))
            pre[i] = math.tanh(s)
        self.state = [(1 - self.leak) * self.state[i] + self.leak * pre[i] for i in range(self.size)]
        return list(self.state)

    def fit_readout(self, inputs: Sequence[Sequence[float]], targets: Sequence[float]) -> None:
        states = []
        self.state = [0.0] * self.size
        for u in inputs:
            states.append(self.step(u))
        self.readout.fit(states, targets)

    def handle(self, input: PerceptionInput) -> Emission:
        vec = _vector_from_input(input, 8)
        st = self.step(vec)
        if self.readout.fitted:
            y = max(0.0, min(1.0, self.readout.predict(st)))
        else:
            y = max(0.0, min(1.0, (sum(st) / len(st) + 1.0) / 2.0))
        body = json.dumps(
            {"point": y, "state_norm": math.sqrt(sum(s * s for s in st))},
            sort_keys=True,
        ).encode()
        return Emission(
            action_class=input.task_descriptor.form,
            payload=body,
            metadata={"module_id": MODULE_ID, "size": str(self.size), "leak": str(self.leak)},
        )

    def justify(self, emission: Emission) -> JustificationToken | None:
        body_obj = {
            "format": FMT,
            "reservoir.size": self.size,
            "reservoir.leak": self.leak,
            "emission_digest": hashlib.sha256(emission.payload).hexdigest(),
        }
        body = json.dumps(body_obj, sort_keys=True, separators=(",", ":")).encode()
        return JustificationToken(
            kind=JustificationKind.KERNEL_BOUND,
            format=FMT,
            body=body,
            signature=hashlib.sha256(b"reservoir-key:" + body).digest(),
        )
