"""v0.3-M1 — Learned ISE + RL-DCA online prediction and promotion gates."""
from __future__ import annotations

import pytest

from organism_sdk.hormone import HormoneBus
from organism_sdk.interoceptive import HealthVector, viability_f
from organism_sdk.learned_ise import LearnedISE
from organism_sdk.workspace import WorkspaceClient


def test_online_update_reduces_prediction_error():
    ise = LearnedISE()
    h = HealthVector(thermal=0.5, energy=0.6)
    # Observed viability systematically above T0 → model should learn positive residual
    observed = min(1.0, viability_f(h) + 0.25)
    errs = [ise.update(h, observed, lr=0.2) for _ in range(40)]
    assert abs(errs[-1]) < abs(errs[0]) or abs(errs[-1]) < 0.05
    assert ise.weights.updates >= 40
    assert ise.last_allostatic is not None


def test_prediction_error_drives_allostatic_and_hormone_nudge():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    bus = HormoneBus(ws)
    ise = LearnedISE()
    h = HealthVector(thermal=0.3, latency_ok=0.4)
    for _ in range(10):
        ise.update(h, 0.2, lr=0.15)
    sig = ise.allostatic_from_prediction_error()
    assert sig.label in {"SAFE", "PAMP", "DANGER"}
    assert sig.stress_delta >= 0.0
    levels = ise.apply_hormone_nudge(bus)
    assert 0.0 <= levels.cortisol <= 1.0
    # Pre-promotion: hormone nudge is signal only — control estimate still blocked
    with pytest.raises(PermissionError):
        ise.estimate(h, for_control=True)


def test_shadow_vs_t0_and_failed_promotion_does_not_actuate():
    ise = LearnedISE(agree_threshold=0.1)
    h = HealthVector(thermal=0.9)
    cmp = ise.shadow_compare(h)
    assert cmp.agree  # untrained ≈ T0
    ise.record_shadow_validate(pass_rate=0.5, ece_ok=False)
    assert not ise.promote()
    assert not ise.control_path_active
    with pytest.raises(PermissionError):
        ise.estimate(h, for_control=True)


def test_successful_promotion_allows_control_estimate():
    ise = LearnedISE()
    h = HealthVector(thermal=0.8)
    for _ in range(5):
        ise.shadow_compare(h)
    ise.record_shadow_validate(pass_rate=0.99, ece_ok=True)
    assert ise.gate.ready() or (
        ise.gate.shadow_validated and ise.gate.calibration_ece_ok
    )
    assert ise.promote()
    st = ise.estimate(h, for_control=True)
    assert st.model_version.startswith("0.3.0-learned")
