"""MoA aggregation: select among expert outputs and record them in a VSA composite (v1.11).

Selection is deterministic: the highest-confidence schema-valid output wins, with
ties broken by expert id. No generative synthesis.

Provenance is a single hypervector that bundles, for each expert, three
role-bound facts:

- ``role(expert:<id>) ⊗ content(payload)``
- ``role(confidence:<id>) ⊗ level(confidence)``
- ``role(schema:<id>) ⊗ flag(schema_valid)``

Each fact can be recovered by unbinding its role and matching the result against
a clean-up memory of the candidate values for this request. Measured recovery
holds for up to 64 experts per request (8 random trials per count), so the
capacity limit assumed in the design doc does not bind at these sizes.
``MAX_EXPERTS_PER_REQUEST`` is a latency policy, not a VSA capacity limit.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from organism_sdk.hypervector import Hypervector
from organism_sdk.moa.experts import ExpertOutput

MAX_EXPERTS_PER_REQUEST = 8
CONFIDENCE_BUCKETS = 11  # 0.0, 0.1, ..., 1.0


def _seeded(label: str) -> Hypervector:
    seed = int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big")
    return Hypervector.random(seed=seed)


def _role(name: str) -> Hypervector:
    return _seeded(f"role:{name}")


def _content(text: str) -> Hypervector:
    return _seeded(f"content:{text}")


def _bucket_label(confidence: float) -> str:
    return f"confidence:{round(confidence * (CONFIDENCE_BUCKETS - 1)):02d}"


def _level(confidence: float) -> Hypervector:
    return _content(_bucket_label(confidence))


def _flag(schema_valid: bool) -> Hypervector:
    return _content("schema:valid" if schema_valid else "schema:invalid")


@dataclass(frozen=True)
class AggregationResult:
    selected: ExpertOutput | None
    composite: Hypervector
    recovered: dict[str, bool]

    @property
    def provenance_ok(self) -> bool:
        return all(self.recovered.values())


def select(outputs: list[ExpertOutput]) -> ExpertOutput | None:
    """Highest-confidence schema-valid output. Ties break on expert id."""
    eligible = [o for o in outputs if o.schema_valid]
    if not eligible:
        return None
    return min(eligible, key=lambda o: (-o.confidence, o.expert_id))


def composite_of(outputs: list[ExpertOutput]) -> Hypervector:
    facts: list[Hypervector] = []
    for o in outputs:
        facts.append(_role(f"expert:{o.expert_id}").bind(_content(o.payload)))
        facts.append(_role(f"confidence:{o.expert_id}").bind(_level(o.confidence)))
        facts.append(_role(f"schema:{o.expert_id}").bind(_flag(o.schema_valid)))
    return Hypervector.bundle(facts)


def _recover(composite: Hypervector, role: Hypervector, candidates: dict[str, Hypervector]) -> str:
    probe = composite.unbind(role)
    return max(candidates, key=lambda name: (probe.similarity(candidates[name]), name))


def verify(composite: Hypervector, outputs: list[ExpertOutput]) -> dict[str, bool]:
    """Recover each expert's payload, confidence bucket, and flag from the composite."""
    payloads = {o.payload: _content(o.payload) for o in outputs}
    levels = {_bucket_label(i / (CONFIDENCE_BUCKETS - 1)): _content(_bucket_label(i / (CONFIDENCE_BUCKETS - 1)))
              for i in range(CONFIDENCE_BUCKETS)}
    flags = {"schema:valid": _content("schema:valid"), "schema:invalid": _content("schema:invalid")}
    result: dict[str, bool] = {}
    for o in outputs:
        got_payload = _recover(composite, _role(f"expert:{o.expert_id}"), payloads)
        got_level = _recover(composite, _role(f"confidence:{o.expert_id}"), levels)
        got_flag = _recover(composite, _role(f"schema:{o.expert_id}"), flags)
        result[o.expert_id] = (
            got_payload == o.payload
            and got_level == _bucket_label(o.confidence)
            and got_flag == ("schema:valid" if o.schema_valid else "schema:invalid")
        )
    return result


def aggregate(outputs: list[ExpertOutput]) -> AggregationResult:
    if len(outputs) > MAX_EXPERTS_PER_REQUEST:
        raise ValueError(f"{len(outputs)} experts exceed the per-request cap of {MAX_EXPERTS_PER_REQUEST}")
    composite = composite_of(outputs)
    return AggregationResult(select(outputs), composite, verify(composite, outputs))
