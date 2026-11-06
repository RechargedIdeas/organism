"""Model-quality record and the gate that reads it (gap H3).

Organism's harness checked faults, soak and speed, never accuracy. A model that is promoted should carry a
record of how it did on a frozen evaluation set, and the promotion gate should read that record. This module
defines the record and a pure gate over it. The evaluation itself stays with the product: NLP-CLI, or any
other learned module, runs its own frozen set and fills in the record.

Metrics are stored as parts per million, as integers. Canonical JSON has no floats, so this keeps the record
hashable and signable. A record is attributed to one model digest and one evaluation-set digest, so it cannot
be moved to another model or another set.

The ``clean`` flag is a claim by the author of the record. The gate cannot check it. It only refuses a record
that does not make the claim when the requirement asks for one.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from organism_sdk.canonical import canonical_text
from organism_sdk.contract import Severity, ValidationIssue

PPM = 1_000_000


def to_ppm(fraction: float) -> int:
    """A fraction in 0..1 as parts per million, rounded to the nearest integer. Rejects NaN and out of range."""
    if not math.isfinite(fraction) or not 0.0 <= fraction <= 1.0:
        raise ValueError("a metric must be a finite fraction in 0..1")
    return round(fraction * PPM)


@dataclass(frozen=True)
class QualityRecord:
    """How one model did on one frozen evaluation set."""

    model_digest: bytes  # SHA-256 of the model artifact, raw bytes
    eval_set_digest: bytes  # SHA-256 of the frozen evaluation file, raw bytes
    eval_set_name: str  # for example "heldout.v5"
    samples: int
    metrics: Mapping[str, int]  # name -> parts per million
    clean: bool  # the set was not read, tuned on or reused before this run

    def digest(self) -> str:
        """The SHA-256 of the record's canonical JSON. Two equal records give the same digest."""
        body = canonical_text(
            {
                "model_digest": self.model_digest.hex(),
                "eval_set_digest": self.eval_set_digest.hex(),
                "eval_set_name": self.eval_set_name,
                "samples": self.samples,
                "metrics": dict(sorted(self.metrics.items())),
                "clean": self.clean,
            }
        )
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class QualityRequirement:
    """A metric that must reach a minimum, in parts per million."""

    metric: str
    minimum_ppm: int


def quality_gate(
    record: QualityRecord,
    requirements: Sequence[QualityRequirement],
    *,
    min_samples: int = 100,
    require_clean: bool = True,
    expected_model_digest: bytes | None = None,
) -> list[ValidationIssue]:
    """The issues that stop a promotion, or an empty list when the record passes. Pure.

    Codes: ``quality_digest_missing``, ``quality_model_mismatch``, ``quality_samples_insufficient``,
    ``quality_not_clean``, ``quality_metric_missing``, ``quality_below_minimum``.
    """
    issues: list[ValidationIssue] = []

    def fail(code: str, path: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.ERROR, code, path, message))

    if not record.model_digest or not record.eval_set_digest:
        fail("quality_digest_missing", "quality.digest", "the record must name the model and the evaluation set")
    if expected_model_digest is not None and record.model_digest != expected_model_digest:
        fail("quality_model_mismatch", "quality.model_digest", "the record was measured on a different model")
    if record.samples < min_samples:
        fail("quality_samples_insufficient", "quality.samples", f"samples={record.samples} required={min_samples}")
    if require_clean and not record.clean:
        fail("quality_not_clean", "quality.clean", "the evaluation set was used before this run")
    for requirement in requirements:
        value = record.metrics.get(requirement.metric)
        if value is None:
            fail("quality_metric_missing", f"quality.metrics.{requirement.metric}", "metric not reported")
        elif value < requirement.minimum_ppm:
            fail(
                "quality_below_minimum",
                f"quality.metrics.{requirement.metric}",
                f"{requirement.metric}={value} ppm, minimum {requirement.minimum_ppm}",
            )
    return issues
