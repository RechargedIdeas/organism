"""Calibration and measured-metabolics evidence (K1b task 7, gaps A5 and A6).

Two pure gates, shaped like the shadow gate in ``registry.py``. A tier that claims calibration (T1 and T2) can show a
calibration record. A module can show a measured metabolic record, which must fit the cost it declared. The registry
checks each gate for the gated states when evidence is supplied, or always for the calibrated tiers and for every
gated promotion when the registry requires it. Vectors: ``evidence.json``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from organism_sdk.contract import MetabolicProfile, ReliabilityTier, Severity, ValidationIssue

# Tiers that claim calibration. T3 says it is uncalibrated, so it makes no claim to check.
CALIBRATED_TIERS: frozenset[ReliabilityTier] = frozenset(
    {ReliabilityTier.T1_CALIBRATED_NONLEARNED, ReliabilityTier.T2_LEARNED_CALIBRATED}
)


@dataclass(frozen=True)
class CalibrationRecord:
    """Calibration measured on held-out data. Every rate is a fraction in 0..1."""

    ece: float  # expected calibration error
    target_coverage: float  # coverage the module's intervals are designed for
    empirical_coverage: float  # coverage the intervals reached on the held-out data
    samples: int
    evidence_digest: bytes = b""


@dataclass(frozen=True)
class CalibrationThreshold:
    """What calibration evidence must show. The defaults are placeholders for the owner to set (see HANDOVER)."""

    max_ece: float = 0.05
    max_coverage_gap: float = 0.05  # target_coverage - empirical_coverage may not exceed this
    min_samples: int = 200


def calibration_gate(record: CalibrationRecord, threshold: CalibrationThreshold) -> list[ValidationIssue]:
    """The first issue that stops a gated promotion, or an empty list when the evidence passes. Pure.

    Codes: ``calibration_evidence_invalid`` (a rate outside 0..1, or NaN), ``calibration_evidence_insufficient``
    (too few samples), ``calibration_evidence_unattributed`` (no evidence digest), ``calibration_ece_exceeded``,
    ``calibration_coverage_short``.
    """

    def fail(code: str, field_path: str, message: str) -> list[ValidationIssue]:
        return [ValidationIssue(Severity.ERROR, code, field_path, message)]

    for name in ("ece", "target_coverage", "empirical_coverage"):
        if not 0.0 <= getattr(record, name) <= 1.0:  # NaN fails this comparison too
            return fail("calibration_evidence_invalid", f"calibration.{name}", f"{name} must be in 0..1")
    if record.samples < threshold.min_samples:
        return fail(
            "calibration_evidence_insufficient",
            "calibration.samples",
            f"samples={record.samples} required={threshold.min_samples}",
        )
    if not record.evidence_digest:
        return fail("calibration_evidence_unattributed", "calibration.evidence_digest", "no evidence digest")
    if record.ece > threshold.max_ece:
        return fail("calibration_ece_exceeded", "calibration.ece", f"ece={record.ece} max={threshold.max_ece}")
    if record.target_coverage - record.empirical_coverage > threshold.max_coverage_gap:
        return fail(
            "calibration_coverage_short",
            "calibration.empirical_coverage",
            f"target={record.target_coverage} empirical={record.empirical_coverage}",
        )
    return []


@dataclass(frozen=True)
class MeasuredMetabolics:
    """What a module cost when it ran on a device. Units are those of ``MetabolicProfile``."""

    device_class: str  # where it ran, for example CPU, GPU or NPU. Recorded, not checked.
    latency_p95_ms: float
    energy_per_inference_j: float
    memory_peak_mb: float
    samples: int
    evidence_digest: bytes = b""


@dataclass(frozen=True)
class MetabolicTolerance:
    """A measured value may exceed the declared one by ``factor`` before it counts as under-declared."""

    factor: float = 1.25
    min_samples: int = 100


def metabolic_gate(
    declared: MetabolicProfile, measured: MeasuredMetabolics, tolerance: MetabolicTolerance
) -> list[ValidationIssue]:
    """Issues that stop a gated promotion because the measurement does not fit the declared cost. Pure.

    Codes: ``measurement_invalid`` (a negative, NaN or infinite value; the first one is reported),
    ``measurement_insufficient``, ``measurement_unattributed``, and ``metabolic_underdeclared`` for every field whose
    measured value exceeds the declared one times ``factor``, in field order.
    """
    for name, value in (
        ("latency_p95_ms", measured.latency_p95_ms),
        ("energy_per_inference_j", measured.energy_per_inference_j),
        ("memory_peak_mb", measured.memory_peak_mb),
    ):
        if not 0.0 <= value < math.inf:
            return [
                ValidationIssue(
                    Severity.ERROR, "measurement_invalid", f"measured.{name}", f"{name} must be finite and >= 0"
                )
            ]
    if measured.samples < tolerance.min_samples:
        return [
            ValidationIssue(
                Severity.ERROR,
                "measurement_insufficient",
                "measured.samples",
                f"samples={measured.samples} required={tolerance.min_samples}",
            )
        ]
    if not measured.evidence_digest:
        return [
            ValidationIssue(
                Severity.ERROR, "measurement_unattributed", "measured.evidence_digest", "no evidence digest"
            )
        ]
    pairs = (
        ("latency_p95_ms", measured.latency_p95_ms, declared.latency_p95_ms),
        ("energy_per_inference_j", measured.energy_per_inference_j, declared.energy_per_inference_j),
        ("memory_peak_mb", measured.memory_peak_mb, declared.memory_peak_mb),
    )
    return [
        ValidationIssue(
            Severity.ERROR,
            "metabolic_underdeclared",
            f"measured.{name}",
            f"measured {measured_value} exceeds declared {declared_value} x {tolerance.factor}",
        )
        for name, measured_value, declared_value in pairs
        if measured_value > declared_value * tolerance.factor
    ]
