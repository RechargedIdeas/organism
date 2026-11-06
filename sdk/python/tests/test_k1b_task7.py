"""K1b task 7 (gaps A5, A6, A7, B6): health and drain, calibration and measured-metabolics evidence, accelerator classes."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from deterministic_engine.engine import DeterministicEngine
from organism_sdk.contract import HardwareRequirement, ReliabilityTier, Severity, SubstrateContract
from organism_sdk.evidence import (
    CalibrationRecord,
    CalibrationThreshold,
    MeasuredMetabolics,
    MetabolicTolerance,
    calibration_gate,
    metabolic_gate,
)
from organism_sdk.health import HealthReport
from organism_sdk.registry import CapabilityFilter, RegistryClient, ShadowValidationRecord

DIGEST = b"\x07" * 32
SHADOW = ShadowValidationRecord(
    invocations=200, incumbent_error=0.25, candidate_error=0.125, p95_latency_ms=3.5, evidence_digest=DIGEST
)
GOOD_CAL = CalibrationRecord(ece=0.02, target_coverage=0.9, empirical_coverage=0.91, samples=500, evidence_digest=DIGEST)
GOOD_MET = MeasuredMetabolics(
    device_class="CPU",
    latency_p95_ms=11.0,
    energy_per_inference_j=0.012,
    memory_peak_mb=110.0,
    samples=300,
    evidence_digest=DIGEST,
)


def _base() -> SubstrateContract:
    return DeterministicEngine().declare_contract()


def _with_tier(c: SubstrateContract, tier: ReliabilityTier) -> SubstrateContract:
    # OC-3: l4_terminal is only valid on T0; clear it when the test retargets the tier.
    l4 = bool(getattr(c.safety, "l4_terminal", False)) and tier is ReliabilityTier.T0_DETERMINISTIC
    return replace(c, safety=replace(c.safety, reliability_tier=tier, l4_terminal=l4))


def _within(c: SubstrateContract) -> MeasuredMetabolics:
    """A measurement equal to the module's own declared cost, so only the test's change can fail the gate."""
    m = c.metabolic
    return MeasuredMetabolics(
        device_class="CPU",
        latency_p95_ms=m.latency_p95_ms,
        energy_per_inference_j=m.energy_per_inference_j,
        memory_peak_mb=m.memory_peak_mb,
        samples=300,
        evidence_digest=DIGEST,
    )


class _Reporting:
    """A module that answers one health status and records its drain deadline."""

    def __init__(self, status: str, score: float) -> None:
        self._report = HealthReport(module_id="x", status=status, score=score)
        self.deadline: datetime | None = None

    def health(self) -> HealthReport:
        return self._report

    def on_drain(self, deadline: datetime) -> None:
        self.deadline = deadline


def _register(reg: RegistryClient, c: SubstrateContract, *, module: object = None, initial: str = "PROPOSED") -> str:
    reg.register(
        c,
        artifact_digest=c.identity.artifact_digest,
        author_signature=b"s",
        module=module,
        initial_state=initial,  # type: ignore[arg-type]
    )
    return c.identity.module_id


# ---- A7: accelerator classes ----------------------------------------------------------------------------------------


def test_gpu_and_npu_classes_are_declared_and_the_flag_must_agree() -> None:
    base = _base()

    def codes(hardware: HardwareRequirement, flag: bool) -> list[str]:
        metabolic = replace(base.metabolic, requires_special_hardware=hardware, requires_gpu=flag)
        return [i.code for i in replace(base, metabolic=metabolic).validate()]

    assert "gpu_flag_mismatch" not in codes(HardwareRequirement.NPU, False)
    assert "gpu_flag_mismatch" not in codes(HardwareRequirement.GPU, True)
    assert "gpu_flag_mismatch" in codes(HardwareRequirement.GPU, False)
    assert "gpu_flag_mismatch" in codes(HardwareRequirement.NONE, True)


# ---- B6: health and drain ---------------------------------------------------------------------------------------------


def test_a_module_without_hooks_reports_healthy() -> None:
    reg = RegistryClient()
    mid = _register(reg, _base())
    report = reg.health(mid)
    assert (report.status, report.score) == ("HEALTHY", 1.0)


def test_a_module_reports_its_own_health_and_unknown_ids_raise() -> None:
    reg = RegistryClient()
    mid = _register(reg, _base(), module=_Reporting("DEGRADED", 0.6))
    report = reg.health(mid)
    assert (report.status, report.score) == ("DEGRADED", 0.6)
    with pytest.raises(KeyError):
        reg.health("no.such.module")


def test_drain_gives_the_module_a_deadline_after_the_timeout() -> None:
    reg = RegistryClient()
    module = _Reporting("HEALTHY", 1.0)
    mid = _register(reg, _base(), module=module, initial="DELIBERATION")
    now = datetime(2027, 1, 1, tzinfo=UTC)
    reg.deregister(mid, drain="immediate", timeout_s=30, now=now)
    assert module.deadline == now + timedelta(seconds=30)
    with pytest.raises(KeyError):
        reg.health(mid)


def test_drain_without_hooks_only_removes_the_module() -> None:
    reg = RegistryClient()
    mid = _register(reg, _base(), initial="EXPLORATION")
    reg.deregister(mid, drain="immediate", timeout_s=5)
    assert reg.query(CapabilityFilter()) == []


# ---- A5: calibration -------------------------------------------------------------------------------------------------


def test_calibration_gate_rejects_nan_and_accepts_the_limit() -> None:
    thr = CalibrationThreshold()
    assert calibration_gate(replace(GOOD_CAL, ece=0.05), thr) == []
    nan_issues = calibration_gate(replace(GOOD_CAL, ece=math.nan), thr)
    assert [i.code for i in nan_issues] == ["calibration_evidence_invalid"]
    assert nan_issues[0].severity == Severity.ERROR


# ---- A6: measured metabolics ----------------------------------------------------------------------------------------


def test_metabolic_gate_rejects_an_infinite_measurement() -> None:
    issues = metabolic_gate(_base().metabolic, replace(GOOD_MET, latency_p95_ms=math.inf), MetabolicTolerance())
    assert [(i.code, i.field_path) for i in issues] == [("measurement_invalid", "measured.latency_p95_ms")]


# ---- promotion with evidence ----------------------------------------------------------------------------------------


def test_a_calibrated_tier_needs_a_calibration_record_when_required() -> None:
    c = _with_tier(_base(), ReliabilityTier.T2_LEARNED_CALIBRATED)
    reg = RegistryClient(require_calibration=True)
    mid = _register(reg, c, initial="SANDBOXED")
    rejected = reg.promote(mid, "SANDBOXED", "SHADOW_VALIDATED", [SHADOW], b"")
    assert rejected.validation_issues[0].code == "calibration_evidence_missing"
    assert reg.query(CapabilityFilter())[0].state == "SANDBOXED"
    assert reg.promote(mid, "SANDBOXED", "SHADOW_VALIDATED", [SHADOW], b"", calibration=GOOD_CAL).accepted


def test_an_uncalibrated_tier_makes_no_calibration_claim() -> None:
    c = _with_tier(_base(), ReliabilityTier.T3_LEARNED_UNCALIBRATED)
    reg = RegistryClient(require_calibration=True)
    mid = _register(reg, c, initial="SANDBOXED")
    assert reg.promote(mid, "SANDBOXED", "SHADOW_VALIDATED", [SHADOW], b"").accepted


def test_measurement_is_required_for_gated_promotions_when_asked() -> None:
    c = _base()
    reg = RegistryClient(require_measurement=True)
    mid = _register(reg, c, initial="SANDBOXED")
    rejected = reg.promote(mid, "SANDBOXED", "SHADOW_VALIDATED", [SHADOW], b"")
    assert rejected.validation_issues[0].code == "measurement_missing"
    assert reg.promote(mid, "SANDBOXED", "SHADOW_VALIDATED", [SHADOW], b"", measured=_within(c)).accepted


def test_supplied_evidence_is_checked_even_when_not_required() -> None:
    c = _base()
    reg = RegistryClient()
    mid = _register(reg, c, initial="SANDBOXED")
    fits = _within(c)
    bad = replace(fits, latency_p95_ms=fits.latency_p95_ms * 10)
    resp = reg.promote(mid, "SANDBOXED", "SHADOW_VALIDATED", [SHADOW], b"", measured=bad)
    assert resp.validation_issues[0].code == "metabolic_underdeclared"
    assert reg.query(CapabilityFilter())[0].state == "SANDBOXED"


def test_ungated_promotions_need_no_evidence_even_when_required() -> None:
    reg = RegistryClient(require_calibration=True, require_measurement=True)
    mid = _register(reg, _with_tier(_base(), ReliabilityTier.T2_LEARNED_CALIBRATED), initial="PROPOSED")
    assert reg.promote(mid, "PROPOSED", "SANDBOXED", [], b"").accepted
