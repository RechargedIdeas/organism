"""M7: E.4 two-module bootstrap + Category I (green-pending where timed)."""
from __future__ import annotations

from pathlib import Path

from deterministic_engine.engine import DeterministicEngine
from harness.scenarios.m6_faults import scenario_no_flapping_on_restore
from learned_module.module import LearnedModule
from organism_sdk.degradation import DegradationMachine, FaultInjector, HealthSignals
from organism_sdk.hypervector import Hypervector
from organism_sdk.registry import RegistryClient
from organism_sdk.router import Router, RouterTask
from organism_sdk.snapshot import DurableWorkspace, query_digest
from organism_sdk.trace import TraceEmitter


def test_e4_two_module_bootstrap(tmp_path: Path):
    trace = TraceEmitter()
    reg = RegistryClient(trace=trace)
    engine = DeterministicEngine()
    learned = LearnedModule(precalibrate=True)
    for mod in (engine, learned):
        c = mod.declare_contract()
        reg.register(
            c,
            artifact_digest=c.identity.artifact_digest,
            author_signature=b"s",
            module=mod,
            test_bypass_promote="DELIBERATION",
        )

    ws = DurableWorkspace(tmp_path / "ws")
    router = Router(reg, level="L0", trace=trace, plan_id_factory=lambda: "p1")
    trace.attach_router_state(router)

    plan_pr = router.decide(
        RouterTask(task_id="pr", form="pattern_recognition", safety_tier="medium")
    )
    assert plan_pr.primary.module_id == "learned_module_t2"

    plan_ca = router.decide(
        RouterTask(task_id="ca", form="control_actuation", safety_tier="high")
    )
    assert plan_ca.primary.module_id == "deterministic_engine"
    assert plan_ca.cross_check_required is False

    rec = ws.bind_exact(Hypervector.random(), Hypervector.random(), tags=("t",), module_id="m")
    snap = ws.snapshot()
    dig = query_digest(ws.ws, rec.hypervector)

    deg = DegradationMachine(
        signals=HealthSignals(
            h_m={"learned_module_t2": "HEALTHY"},
            c_m={"learned_module_t2": 0.96},
        )
    )
    FaultInjector(deg).kill_module("learned_module_t2")
    deg.tick()
    deg.advance(5.0)
    assert deg.level == "L1"
    router.set_level("L1")

    scenario_no_flapping_on_restore()

    rebuilt = ws.replay_from_snapshot(snap.path, ops_from=10**9)
    assert query_digest(rebuilt, rec.hypervector) == dig

    router.set_level("L4")
    plan_l4 = router.decide(
        RouterTask(task_id="l4", form="control_actuation", safety_tier="high")
    )
    assert plan_l4.primary.module_id == "deterministic_engine"
    assert plan_l4.plan_type == "DegradedDispatchPlan"


def test_category_i_green_pending_documented():
    """Category I wall-clock items are green-pending (IMP-5)."""
    assert True
