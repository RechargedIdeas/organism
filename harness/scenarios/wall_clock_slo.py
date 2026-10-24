"""Wall-clock hysteresis / transition physiology (perf:slo, Category I).

Fast path uses T_DOWN_FAST / T_UP_FAST (T_up ≥ 5·T_down) so default CI stays
under ~15s wall while proving the same state machine under time.monotonic().

Full E-5 1b (~480s) uses production B.4 defaults and is opt-in via
ORGANISM_WALL_CLOCK_FULL=1.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

from organism_sdk.degradation import (
    T_DOWN,
    T_DOWN_FAST,
    T_UP,
    T_UP_FAST,
    DegradationMachine,
    FaultInjector,
    HealthSignals,
)

POLL_S = 0.05
# Allow scheduling jitter above the hysteresis window.
SLO_MARGIN_S = 0.75


@dataclass
class WallClockResult:
    elapsed_s: float
    level: str
    transitions: list[tuple[str, str, str]]
    machine_now_s: float


def _fresh(t_down: dict[str, float], t_up: dict[str, float]) -> tuple[DegradationMachine, FaultInjector]:
    m = DegradationMachine(
        signals=HealthSignals(
            h_m={"learned_module_t2": "HEALTHY", "deterministic_engine": "HEALTHY"},
            c_m={"learned_module_t2": 0.96},
            thermal=0.8,
            neural_modules=("learned_module_t2",),
            leading_predictive=("learned_module_t2",),
        ),
        t_down=dict(t_down),
        t_up=dict(t_up),
    )
    return m, FaultInjector(m)


def _wait_until(
    m: DegradationMachine,
    predicate,
    *,
    timeout_s: float,
    t0: float,
) -> float:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        m.sync_wall_clock(time.monotonic())
        if predicate(m):
            return time.monotonic() - t0
        time.sleep(POLL_S)
    m.sync_wall_clock(time.monotonic())
    raise AssertionError(
        f"timeout after {timeout_s:.2f}s; level={m.level} transitions={m.transitions}"
    )


def _band(expected_s: float) -> tuple[float, float]:
    """Documented SLO band: [expected, expected + margin]. Early fire is a fail."""
    return (expected_s - 0.05, expected_s + SLO_MARGIN_S)


def scenario_fast_l0_l1_wall() -> WallClockResult:
    """L0→L1 under real time with scaled T_down[L1]."""
    m, inj = _fresh(T_DOWN_FAST, T_UP_FAST)
    t0 = time.monotonic()
    m.sync_wall_clock(t0)
    inj.kill_module("learned_module_t2")
    m.sync_wall_clock(time.monotonic())  # arm timer
    expected = T_DOWN_FAST["L1"]
    lo, hi = _band(expected)
    elapsed = _wait_until(m, lambda x: x.level == "L1", timeout_s=hi + 1.0, t0=t0)
    assert lo <= elapsed <= hi, f"L0→L1 elapsed {elapsed:.3f}s not in [{lo},{hi}]"
    assert m.transitions[-1][0:2] == ("L0", "L1")
    return WallClockResult(elapsed, m.level, list(m.transitions), m.now_s)


def scenario_fast_no_flapping_and_recovery() -> WallClockResult:
    """Scaled E-5 1b physiology: L0→L1→L2→L1→L0 under wall clock; no early up."""
    m, inj = _fresh(T_DOWN_FAST, T_UP_FAST)
    t0 = time.monotonic()
    m.sync_wall_clock(t0)

    inj.kill_module("learned_module_t2")
    m.sync_wall_clock(time.monotonic())
    e1 = _wait_until(
        m, lambda x: x.level == "L1",
        timeout_s=T_DOWN_FAST["L1"] + SLO_MARGIN_S + 1.0, t0=t0,
    )
    lo, hi = _band(T_DOWN_FAST["L1"])
    assert lo <= e1 <= hi, f"L0→L1 {e1:.3f} not in [{lo},{hi}]"

    inj.fail_module("learned_module_t2")
    m.sync_wall_clock(time.monotonic())
    t_arm_l2 = time.monotonic()
    e2 = _wait_until(
        m, lambda x: x.level == "L2",
        timeout_s=T_DOWN_FAST["L2"] + SLO_MARGIN_S + 1.0, t0=t_arm_l2,
    )
    lo, hi = _band(T_DOWN_FAST["L2"])
    assert lo <= e2 <= hi, f"L1→L2 {e2:.3f} not in [{lo},{hi}]"

    before = len(m.transitions)
    inj.restore_module("learned_module_t2")
    m.signals.causal_ok = True
    m.signals.thermal = 0.8
    m.sync_wall_clock(time.monotonic())
    # Hold for ~half T_up[L2] — must not flap upward.
    hold = T_UP_FAST["L2"] * 0.45
    hold_deadline = time.monotonic() + hold
    while time.monotonic() < hold_deadline:
        m.sync_wall_clock(time.monotonic())
        time.sleep(POLL_S)
    assert len(m.transitions) == before, f"flapping: {m.transitions}"
    assert m.level == "L2"

    t_arm_up = time.monotonic()
    # Remaining time to complete T_up[L2] from original arm (~0.55 left + margin).
    e3 = _wait_until(
        m, lambda x: x.level == "L1",
        timeout_s=T_UP_FAST["L2"] + SLO_MARGIN_S + 1.0, t0=t_arm_up,
    )
    # After partial hold, remaining expected ≈ 0.55 * T_up; allow broad band.
    assert e3 <= T_UP_FAST["L2"] + SLO_MARGIN_S
    assert e3 >= T_UP_FAST["L2"] * 0.40  # must have waited the remainder

    m.sync_wall_clock(time.monotonic())  # re-arm L1→L0 after clear-on-transition
    t_arm_l0 = time.monotonic()
    e4 = _wait_until(
        m, lambda x: x.level == "L0",
        timeout_s=T_UP_FAST["L1"] + SLO_MARGIN_S + 1.0, t0=t_arm_l0,
    )
    lo, hi = _band(T_UP_FAST["L1"])
    assert lo <= e4 <= hi, f"L1→L0 {e4:.3f} not in [{lo},{hi}]"

    downs = [t for t in m.transitions if t[0] < t[1] or (t[0], t[1]) in (("L0", "L1"), ("L1", "L2"))]
    ups = [t for t in m.transitions if t[2] == "recovery"]
    assert len(m.transitions) == 4, m.transitions
    assert len(ups) == 2
    assert downs  # sanity
    total = time.monotonic() - t0
    return WallClockResult(total, m.level, list(m.transitions), m.now_s)


def scenario_e5_1b_full_wall_clock() -> WallClockResult:
    """Full production hysteresis E-5 1b (~480s). Opt-in only."""
    if os.environ.get("ORGANISM_WALL_CLOCK_FULL") != "1":
        raise RuntimeError("set ORGANISM_WALL_CLOCK_FULL=1 to run full 480s wall-clock")

    m, inj = _fresh(T_DOWN, T_UP)
    t0 = time.monotonic()
    m.sync_wall_clock(t0)

    inj.kill_module("learned_module_t2")
    m.sync_wall_clock(time.monotonic())
    _wait_until(m, lambda x: x.level == "L1", timeout_s=T_DOWN["L1"] + 10, t0=t0)

    inj.fail_module("learned_module_t2")
    m.sync_wall_clock(time.monotonic())
    t1 = time.monotonic()
    _wait_until(m, lambda x: x.level == "L2", timeout_s=T_DOWN["L2"] + 15, t0=t1)

    inj.restore_module("learned_module_t2")
    m.signals.causal_ok = True
    m.signals.thermal = 0.8
    m.sync_wall_clock(time.monotonic())
    t2 = time.monotonic()
    _wait_until(m, lambda x: x.level == "L1", timeout_s=T_UP["L2"] + 30, t0=t2)

    m.sync_wall_clock(time.monotonic())
    t3 = time.monotonic()
    _wait_until(m, lambda x: x.level == "L0", timeout_s=T_UP["L1"] + 30, t0=t3)

    total = time.monotonic() - t0
    # Nominal: 5 + 30 + 300 + 120 = 455s; band [450, 480]
    assert 450.0 <= total <= 480.0, f"full 1b elapsed {total:.1f}s outside [450,480]"
    assert len(m.transitions) == 4, m.transitions
    return WallClockResult(total, m.level, list(m.transitions), m.now_s)
