"""spectral — T1 FEATURE_EXTRACTOR: Haar wavelet spectral front-end."""
from __future__ import annotations

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
from organism_sdk.justification import Emission
from organism_sdk.module import OrganismModule
from _common.contract_factory import make_contract

MODULE_ID = "spectral"
MODULE_VERSION = "1.0.0"
FMT = "typed-json:spectral-features/v1"

def _vector_from_input(inp: PerceptionInput, dim: int = 16) -> list[float]:
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


def haar_dwt(x: Sequence[float]) -> list[float]:
    x = list(x)
    if len(x) % 2:
        x.append(0.0)
    approx, detail = [], []
    for i in range(0, len(x), 2):
        approx.append((x[i] + x[i + 1]) / math.sqrt(2))
        detail.append((x[i] - x[i + 1]) / math.sqrt(2))
    return approx + detail


def soft_threshold(coeffs: Sequence[float], t: float = 0.1) -> list[float]:
    out = []
    for c in coeffs:
        if abs(c) <= t:
            out.append(0.0)
        else:
            out.append(math.copysign(abs(c) - t, c))
    return out


class SpectralModule(OrganismModule):
    def __init__(self, *, threshold: float = 0.1, basis: str = "haar") -> None:
        self.threshold = threshold
        self.basis = basis
        self._status = "HEALTHY"
        self._score = 1.0

    def declare_contract(self):
        return make_contract(
            module_id=MODULE_ID,
            version=MODULE_VERSION,
            role=ModuleRole.FEATURE_EXTRACTOR,
            tier=ReliabilityTier.T1_CALIBRATED_NONLEARNED,
            modalities=(Modality.TEMPORAL_STREAM, Modality.WAVELET_COEFFS, Modality.DENSE_VECTOR),
            required_modalities=(Modality.DENSE_VECTOR,),
            output_form=OutputForm.FEATURE_VECTOR,
            uncertainty=UncertaintyKind.NONE,
            determinism=Determinism.DETERMINISTIC,
            justification_kind=JustificationKind.NONE,
            justification_format=FMT,
            required_fields=(),
            write_tags=("spectral", "memory"),
            shape_dims=(16,),
            failure_name="spectral_basis_fail",
        )

    def health(self) -> HealthReport:
        return HealthReport(module_id=MODULE_ID, status=self._status, score=self._score)

    def transform(self, seq: Sequence[float]) -> list[float]:
        coeffs = haar_dwt(seq) if self.basis == "haar" else list(seq)
        return soft_threshold(coeffs, self.threshold)

    def handle(self, input: PerceptionInput) -> Emission:
        seq = _vector_from_input(input, 16)
        feats = self.transform(seq)
        energy = sum(f * f for f in feats)
        body = json.dumps(
            {"features": feats, "energy": energy, "basis": self.basis},
            sort_keys=True,
        ).encode()
        return Emission(
            action_class=input.task_descriptor.form,
            payload=body,
            metadata={"module_id": MODULE_ID, "threshold": str(self.threshold)},
        )
