"""F extension Categories J–O — runnable subset (v0.2)."""
from __future__ import annotations

from dataclasses import replace

from deterministic_engine.engine import DeterministicEngine

from organism_sdk.apoptosis import ApoptosisService, MemoryExport
from organism_sdk.autonomic import AutonomicController, AutonomicConfig
from organism_sdk.circadian import CircadianClock
from organism_sdk.hormone import HormoneBus
from organism_sdk.hypervector import Hypervector
from organism_sdk.immune import ImmuneLayer
from organism_sdk.interoceptive import HealthVector, InteroceptiveStateEstimator
from organism_sdk.morphogenesis import DevelopmentalGenome, DevelopmentalStage, MorphogenesisTracker
from organism_sdk.trace import TraceEmitter, V02TraceSink
from organism_sdk.workspace import WorkspaceClient


def _tr():
    tr = TraceEmitter(); tr.attach_v02_sink(V02TraceSink()); return tr


def scenario_j1_ise_crisis_precursor():
    ise = InteroceptiveStateEstimator(viability_floor=0.3)
    st = None
    for v in [0.95, 0.7, 0.5, 0.36]:
        st = ise.estimate(HealthVector(thermal=v, latency_ok=v, calibration=v, energy=v, module_health_min=v))
    assert st and (st.crisis_precursor or st.request_setpoint_adaptation)


def scenario_k1_cortisol_release():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    bus = HormoneBus(ws, trace=_tr())
    levels = bus.compute_release(stress_load=0.9, viability_score=0.2, crisis_precursor_count=2)
    bus.write_telemetry_window(levels)
    assert bus.read_workspace_hormone_state().cortisol > 0.3


def scenario_l1_danger_surveil():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    immune = ImmuneLayer(ws, trace=_tr())
    antigen = Hypervector.random(seed=42); immune._detectors.insert(0, antigen)
    d = immune.ingress(antigen)
    assert d.decision in ("SURVEIL", "QUARANTINE") and ws.read_by_tag(["immune_decision"])


def scenario_m1_crisis_mode():
    t = [0.0]
    ac = AutonomicController(trace=_tr(), clock=lambda: t[0], config=AutonomicConfig())
    ac.tick(viability=0.1, crisis_precursor=True)
    assert ac.mode == "CRISIS"


def scenario_n2_t0_reject():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    svc = ApoptosisService(ws)
    c = DeterministicEngine().declare_contract()
    c2 = replace(c, lifecycle=replace(c.lifecycle, self_termination_permitted=True))
    r = svc.begin_self_terminate(c2, cause="x", memory=MemoryExport({}, [], [], {}), successor_available=True, control_affecting=False)
    assert not r.accepted and r.reason == "AP-2"


def scenario_o1_stage_fail():
    tr = MorphogenesisTracker()
    g = DevelopmentalGenome("g", [DevelopmentalStage(1, "a", locus="a"), DevelopmentalStage(2, "b", locus="b"), DevelopmentalStage(3, "c", locus="c")])
    tr.register_genome("m", g)
    tr.run_stage("m", pass_stage=True); tr.run_stage("m", pass_stage=True); tr.run_stage("m", pass_stage=False)
    assert g.stages[0].status == "PASSED" and g.mutation_locus == "c"


def scenario_o4_circadian_crisis():
    clock = CircadianClock(rest_start=0.0, rest_end=1.0)
    st = clock.advance(0.0, crisis=True)
    assert st.melatonin_baseline == 0.0 and not st.in_rest


SCENARIOS = {"J1": scenario_j1_ise_crisis_precursor, "K1": scenario_k1_cortisol_release, "L1": scenario_l1_danger_surveil,
             "M1": scenario_m1_crisis_mode, "N2": scenario_n2_t0_reject, "O1": scenario_o1_stage_fail, "O4": scenario_o4_circadian_crisis}
