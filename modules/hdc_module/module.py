"""hdc_module — T1 MEMORY: HDC workspace helper / fingerprint beyond Hypervector primitives."""
from __future__ import annotations

import hashlib
import json

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
from organism_sdk.hypervector import Hypervector
from organism_sdk.inputs import PerceptionInput
from organism_sdk.justification import Emission
from organism_sdk.module import OrganismModule
from _common.contract_factory import make_contract

MODULE_ID = "hdc_module"
MODULE_VERSION = "1.0.0"
FMT = "typed-json:hdc-fingerprint/v1"


class HDCModule(OrganismModule):
    def __init__(self, *, seed: int = 7) -> None:
        self._seed = seed
        self._codebook: dict[str, Hypervector] = {}
        self._memory: list[tuple[str, Hypervector]] = []
        self._status = "HEALTHY"
        self._score = 1.0
        for name in ("role", "filler", "context", "query"):
            self._codebook[name] = Hypervector.random(seed=seed + abs(hash(name)) % 10_000)

    def declare_contract(self):
        return make_contract(
            module_id=MODULE_ID,
            version=MODULE_VERSION,
            role=ModuleRole.MEMORY,
            tier=ReliabilityTier.T1_CALIBRATED_NONLEARNED,
            modalities=(Modality.HYPERVECTOR, Modality.DENSE_VECTOR, Modality.TEXT),
            required_modalities=(Modality.DENSE_VECTOR,),
            output_form=OutputForm.HYPERVECTOR,
            uncertainty=UncertaintyKind.NONE,
            determinism=Determinism.SEEDED,
            justification_kind=JustificationKind.NONE,
            justification_format=FMT,
            required_fields=(),
            write_tags=("hdc", "memory"),
            failure_name="workspace_corruption",
        )

    def health(self) -> HealthReport:
        return HealthReport(module_id=MODULE_ID, status=self._status, score=self._score)

    def encode_token(self, token: str) -> Hypervector:
        if token not in self._codebook:
            self._codebook[token] = Hypervector.random(seed=self._seed + abs(hash(token)) % 1_000_000)
        return self._codebook[token]

    def fingerprint(self, tokens: list[str]) -> Hypervector:
        if not tokens:
            return Hypervector.random(seed=self._seed)
        hvs = [self.encode_token(t) for t in tokens]
        return Hypervector.bundle(hvs)

    def store(self, key: str, hv: Hypervector) -> None:
        self._memory.append((key, hv))
        if len(self._memory) > 256:
            self._memory = self._memory[-256:]

    def retrieve(self, query: Hypervector, k: int = 3) -> list[tuple[str, float]]:
        scored = [(key, hv.similarity(query)) for key, hv in self._memory]
        scored.sort(key=lambda x: -x[1])
        return scored[:k]

    def handle(self, input: PerceptionInput) -> Emission:
        tid = input.task_descriptor.task_id
        tokens = [tid, input.task_descriptor.form, input.task_descriptor.safety_tier]
        fp = self.fingerprint(tokens)
        bound = self._codebook["role"].bind(fp)
        self.store(tid, bound)
        hits = self.retrieve(bound, k=3)
        body = json.dumps(
            {
                "fingerprint_bytes": len(fp.to_bytes_be()),
                "hits": [{"key": k, "sim": s} for k, s in hits],
                "memory_size": len(self._memory),
            },
            sort_keys=True,
        ).encode()
        return Emission(
            action_class=input.task_descriptor.form,
            payload=body,
            metadata={"module_id": MODULE_ID, "seed": str(self._seed)},
        )
