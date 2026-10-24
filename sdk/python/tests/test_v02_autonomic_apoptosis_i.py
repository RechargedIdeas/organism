"""Artifact I / Categories M–N — Autonomic + Apoptosis."""
from __future__ import annotations

from dataclasses import replace

import pytest
from deterministic_engine.engine import DeterministicEngine

from organism_sdk.apoptosis import ApoptosisService, MemoryExport
from organism_sdk.autonomic import AutonomicController, AutonomicConfig, RouterExposedParams
from organism_sdk.contract import ReliabilityTier as RT
from organism_sdk.registry import RegistryClient
from organism_sdk.router import Router, RouterTask
from organism_sdk.trace import AutonomicTraceEntry, TraceEmitter, V02TraceSink
from organism_sdk.workspace import WorkspaceClient


def test_m1_crisis_precursor_enters_crisis_traced():
    tr = TraceEmitter(); tr.attach_v02_sink(V02TraceSink())
    t = [0.0]
    ac = AutonomicController(trace=tr, config=AutonomicConfig(t_down_s=0.01), clock=lambda: t[0])
    params = ac.tick(viability=0.2, crisis_precursor=True)
    assert ac.mode == "CRISIS" and params.exploration_budget == 0.0 and params.cross_check_frequency == 2.0
    assert any(isinstance(e, AutonomicTraceEntry) for e in tr.entries)


def test_m2_recovery_hysteresis_no_flap():
    t = [0.0]
    ac = AutonomicController(config=AutonomicConfig(t_down_s=0.05, t_up_s=0.3, t_recovery_dwell_s=0.2), clock=lambda: t[0])
    ac.tick(viability=0.1, crisis_precursor=True)
    assert ac.mode == "CRISIS"
    t[0] += 0.01
    ac.tick(viability=0.95, crisis_precursor=False)
    assert ac.mode == "CRISIS"
    t[0] += 0.25
    ac.tick(viability=0.95)
    if ac.mode == "CRISIS":
        t[0] += 0.3
        ac.tick(viability=0.95)
    assert ac.mode in ("RECOVERY", "PARASYMPATHETIC")


def test_m3_autonomic_cannot_select_module():
    ac = AutonomicController()
    with pytest.raises(PermissionError):
        ac.select_module_for_task("task")
    assert ac.select_module_attempts == 1
    eng = DeterministicEngine(); reg = RegistryClient(); c = eng.declare_contract()
    reg.register(c, c.identity.artifact_digest, b"s", module=eng, test_bypass_promote="DELIBERATION")
    plan = Router(reg, autonomic_params=RouterExposedParams()).decide(RouterTask(task_id="t", form="control_actuation", safety_tier="high"))
    assert plan.disposition == "DISPATCH"


def test_m4_oscillation_bounded_by_hysteresis():
    t = [0.0]
    ac = AutonomicController(config=AutonomicConfig(t_down_s=0.1, t_up_s=0.5), clock=lambda: t[0])
    before = len(ac.transitions)
    for i in range(20):
        ac.tick(viability=0.55 if i % 2 == 0 else 0.65, cortisol=0.4)
        t[0] += 0.02
    assert len(ac.transitions) - before <= 2


def test_n1_self_terminate_with_successor():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    tr = TraceEmitter(); tr.attach_v02_sink(V02TraceSink())
    svc = ApoptosisService(ws, trace=tr)
    c = DeterministicEngine().declare_contract()
    c2 = replace(c, safety=replace(c.safety, reliability_tier=RT.T2_LEARNED_CALIBRATED, may_actuate=False),
                 lifecycle=replace(c.lifecycle, self_termination_permitted=True),
                 identity=replace(c.identity, module_id="learned_apoptosis_t2"))
    result = svc.begin_self_terminate(c2, cause="entropy_collapse", memory=MemoryExport({"w": 1}, [{"id": 1}], ["entropy_collapse"], {"ece": 0.01}),
                                      successor_available=True, control_affecting=False)
    assert result.accepted and result.state == "SUCCEEDED" and result.death_certificate
    assert ws.read_by_tag(["death_certificate"])


def test_n2_t0_cannot_self_terminate():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    svc = ApoptosisService(ws)
    c = DeterministicEngine().declare_contract()
    c2 = replace(c, lifecycle=replace(c.lifecycle, self_termination_permitted=True))
    result = svc.begin_self_terminate(c2, cause="x", memory=MemoryExport({}, [], [], {}), successor_available=True, control_affecting=False)
    assert not result.accepted and result.reason == "AP-2"


def test_n3_control_affecting_without_successor_degraded():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    svc = ApoptosisService(ws)
    c = DeterministicEngine().declare_contract()
    c2 = replace(c, safety=replace(c.safety, reliability_tier=RT.T2_LEARNED_CALIBRATED),
                 lifecycle=replace(c.lifecycle, self_termination_permitted=True),
                 identity=replace(c.identity, module_id="ctrl_t2"))
    result = svc.begin_self_terminate(c2, cause="staleness", memory=MemoryExport({}, [], [], {}), successor_available=False, control_affecting=True)
    assert not result.accepted and result.state == "DEGRADED" and result.reason == "AP-3"


def test_autonomic_params_modulate_router():
    eng = DeterministicEngine(); reg = RegistryClient(); c = eng.declare_contract()
    reg.register(c, c.identity.artifact_digest, b"s", module=eng, test_bypass_promote="DELIBERATION")
    router = Router(reg, autonomic_params=RouterExposedParams(exploration_budget=0.0, preemption_class="PREEMPT_RESEARCH"))
    plan = router.decide(RouterTask(task_id="r1", form="generation", safety_tier="research"))
    assert plan.disposition == "HOLD"
