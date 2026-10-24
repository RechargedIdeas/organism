"""perf:slo / Category I wall-clock physiology tests."""
from __future__ import annotations

import os

import pytest

from harness.scenarios.wall_clock_slo import (
    scenario_e5_1b_full_wall_clock,
    scenario_fast_l0_l1_wall,
    scenario_fast_no_flapping_and_recovery,
)


def test_wall_clock_l0_l1_fast():
    r = scenario_fast_l0_l1_wall()
    assert r.level == "L1"
    assert r.elapsed_s > 0.3


def test_wall_clock_e5_1b_fast_physiology():
    """Scaled E-5 1b under time.monotonic(); proves hysteresis + no flapping."""
    r = scenario_fast_no_flapping_and_recovery()
    assert r.level == "L0"
    assert len(r.transitions) == 4
    assert r.transitions[0][0:2] == ("L0", "L1")
    assert r.transitions[1][0:2] == ("L1", "L2")
    assert r.transitions[2][0:2] == ("L2", "L1")
    assert r.transitions[3][0:2] == ("L1", "L0")


@pytest.mark.slow
def test_e5_1b_wall_clock_480s():
    """Full B.4 hysteresis E-5 1b (~480s). Skip unless ORGANISM_WALL_CLOCK_FULL=1."""
    if os.environ.get("ORGANISM_WALL_CLOCK_FULL") != "1":
        pytest.skip("opt-in: ORGANISM_WALL_CLOCK_FULL=1 (≈8 min wall clock)")
    r = scenario_e5_1b_full_wall_clock()
    assert r.level == "L0"
    assert 450.0 <= r.elapsed_s <= 480.0
