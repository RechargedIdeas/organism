"""B.6 / E.6 fault-injection scenarios (executable, virtual clock)."""
from __future__ import annotations

from organism_sdk.degradation import DegradationMachine, FaultInjector, HealthSignals


def scenario_kill_learned_l0_to_l1() -> DegradationMachine:
    m = DegradationMachine(
        signals=HealthSignals(
            h_m={"learned_module_t2": "HEALTHY", "deterministic_engine": "HEALTHY"},
            c_m={"learned_module_t2": 0.96},
            neural_modules=("learned_module_t2",),
            leading_predictive=("learned_module_t2",),
        )
    )
    inj = FaultInjector(m)
    inj.kill_module("learned_module_t2")
    m.tick()  # arm T_down[L1] timer at t=0
    m.advance(5.0)  # T_down[L1]
    assert m.level == "L1", m.level
    assert m.transitions[-1][2]
    return m


def scenario_persistent_failure_l1_to_l2() -> DegradationMachine:
    m = scenario_kill_learned_l0_to_l1()
    inj = FaultInjector(m)
    inj.fail_module("learned_module_t2")
    m.tick()  # arm T_down[L2]
    m.advance(30.0)
    assert m.level == "L2", m.level
    return m


def scenario_no_flapping_on_restore() -> DegradationMachine:
    m = scenario_persistent_failure_l1_to_l2()
    inj = FaultInjector(m)
    inj.restore_module("learned_module_t2")
    m.signals.causal_ok = True
    m.signals.thermal = 0.8
    before = len(m.transitions)
    m.tick()  # arm recovery timers
    m.advance(60.0)  # < T_up[L2]=300 — must NOT flap
    assert len(m.transitions) == before, "flapping detected"
    assert m.level == "L2"
    m.advance(240.0)  # total 300 from arm
    assert m.level == "L1", m.level
    m.tick()  # re-arm L1→L0 (cleared on transition)
    m.advance(120.0)
    assert m.level == "L0", m.level
    assert len([t for t in m.transitions if t[2] == "recovery"]) >= 2
    return m


def scenario_trace_corrupt_to_l4() -> DegradationMachine:
    m = DegradationMachine(level="L3", signals=HealthSignals(det_ok=True, trace_ok=True))
    inj = FaultInjector(m)
    inj.corrupt_trace_sink()
    m.tick()
    m.advance(10.0)
    assert m.level == "L4"
    return m


def scenario_byzantine_to_l4() -> DegradationMachine:
    m = DegradationMachine(level="L3", signals=HealthSignals())
    inj = FaultInjector(m)
    for _ in range(3):
        inj.byzantine_strike()
    m.tick()
    m.advance(10.0)
    assert m.level == "L4"
    return m
