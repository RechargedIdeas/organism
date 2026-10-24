"""v0.4-M1 soak / stability tests."""
from __future__ import annotations

import os

import pytest

from harness.scenarios.v04_soak import run_soak, run_soak_extended


def test_soak_fast_ci_multi_window():
    r = run_soak(windows=24, max_bindings=48)
    assert r.windows == 24
    assert r.plans == 24
    assert r.hormone_windows == 24
    assert r.routing_trace_count >= 24
    assert not r.flapping
    assert r.binding_count_final <= 56
    assert r.binding_count_peak >= r.binding_count_final
    assert "L0" in r.levels_seen or "L1" in r.levels_seen


def test_soak_workspace_gc_bounds_growth():
    r = run_soak(windows=40, max_bindings=32)
    assert r.binding_count_final <= 40
    assert r.hormone_windows == 40


@pytest.mark.slow
def test_soak_extended_opt_in():
    if os.environ.get("ORGANISM_SOAK_FULL") != "1":
        pytest.skip("opt-in: ORGANISM_SOAK_FULL=1")
    r = run_soak_extended(windows=240)
    assert r.windows == 240
    assert not r.flapping
    assert r.routing_trace_count >= 240
