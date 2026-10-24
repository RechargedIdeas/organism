"""F extension Categories J–O — full runnable matrix (v0.2)."""
from __future__ import annotations

import math
import time
from dataclasses import replace

from deterministic_engine.engine import DeterministicEngine

from organism_sdk.apoptosis import ApoptosisService, MemoryExport
from organism_sdk.autonomic import AutonomicController, AutonomicConfig, RouterExposedParams
from organism_sdk.circadian import CircadianClock, kleiber_declared_share, metabolic_inefficiency
from organism_sdk.contract import ReliabilityTier as RT
from organism_sdk.federation import FederationGate, FederationUnsupported
from organism_sdk.hormone import (
    HormoneBus,
    HormoneLevels,
    HormoneReceptor,
    apply_hormone_to_module_params,
)
from organism_sdk.hypervector import Hypervector
from organism_sdk.immune import ImmuneLayer
from organism_sdk.interoceptive import HealthVector, InteroceptiveStateEstimator
from organism_sdk.learned_ise import LearnedISE
from organism_sdk.metamodel import MetamodelDisabled, MetamodelTracker
from organism_sdk.morphogenesis import DevelopmentalGenome, DevelopmentalStage, MorphogenesisTracker
from organism_sdk.registry import RegistryClient
from organism_sdk.router import Router, RouterTask
from organism_sdk.trace import HormoneTraceEntry, ImmuneTraceEntry, TraceEmitter, V02TraceSink
from organism_sdk.workspace import WorkspaceClient


def _tr():
    tr = TraceEmitter()
    tr.attach_v02_sink(V02TraceSink())
    return tr


def _t2_contract(module_id: str = "learned_apoptosis_t2"):
    c = DeterministicEngine().declare_contract()
    return replace(
        c,
        safety=replace(c.safety, reliability_tier=RT.T2_LEARNED_CALIBRATED, may_actuate=False),
        lifecycle=replace(c.lifecycle, self_termination_permitted=True),
        identity=replace(c.identity, module_id=module_id),
    )


# ── Category J ──────────────────────────────────────────────────────────────


def scenario_j1_ise_crisis_precursor():
    ise = InteroceptiveStateEstimator(viability_floor=0.3)
    st = None
    for v in [0.95, 0.7, 0.5, 0.36]:
        st = ise.estimate(HealthVector(thermal=v, latency_ok=v, calibration=v, energy=v, module_health_min=v))
    assert st and (st.crisis_precursor or st.request_setpoint_adaptation)


def scenario_j2_ise_offline_fallback():
    ise = InteroceptiveStateEstimator()
    ise.set_offline(True)
    st = ise.estimate(HealthVector())
    assert st.model_version.endswith("offline")
    assert math.isnan(st.viability_score)
    # Reactive B path: autonomic still ticks without ISE viability
    ac = AutonomicController(config=AutonomicConfig())
    ac.tick(viability=0.5, crisis_precursor=False)  # no silent skip
    assert ac.mode in ("PARASYMPATHETIC", "SYMPATHETIC", "CRISIS", "RECOVERY")


def scenario_j3_replay_interoceptive():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    ise = InteroceptiveStateEstimator(ws)
    st = ise.estimate(HealthVector(thermal=0.8, energy=0.9))
    rec = ise.write_state(st)
    got = ws.read_by_tag(["interoceptive_state"])[0]
    assert got.payload["viability_score"] == st.viability_score == rec.payload["viability_score"]
    assert got.payload["predicted_trajectory"]["viability_at_horizon"] == st.predicted_trajectory.viability_at_horizon


def scenario_j4_false_high_probe():
    ise = InteroceptiveStateEstimator(viability_floor=0.3)
    # Reported components look healthy but probe failed / h_m cliff
    st = ise.estimate(
        HealthVector(thermal=0.95, latency_ok=0.95, calibration=0.95, energy=0.95, module_health_min=0.95),
        probe_ok=False,
        cross_check_hm=0.1,
    )
    assert st.crisis_precursor
    ac = AutonomicController()
    ac.tick(viability=st.viability_score, crisis_precursor=st.crisis_precursor)
    assert ac.mode != "PARASYMPATHETIC"


# ── Category K ──────────────────────────────────────────────────────────────


def scenario_k1_cortisol_release():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    bus = HormoneBus(ws, trace=_tr())
    levels = bus.compute_release(stress_load=0.9, viability_score=0.2, crisis_precursor_count=2)
    bus.write_telemetry_window(levels)
    assert bus.read_workspace_hormone_state().cortisol > 0.3


def scenario_k2_staleness_trace():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    tr = _tr()
    bus = HormoneBus(ws, trace=tr)
    bus.write_telemetry_window(HormoneLevels(cortisol=0.55, window_id="w1"))
    time.sleep(0.02)
    reading = bus.read_mirror(consumer="router")
    assert reading.staleness_ms >= 15.0
    he = [e for e in tr.entries if isinstance(e, HormoneTraceEntry)]
    assert he and he[-1].staleness_ms == reading.staleness_ms


def scenario_k3_cortisol_modulation_shield():
    levels = HormoneLevels(cortisol=0.9)
    receptors = [
        HormoneReceptor("CORTISOL", "THRESHOLD_GATE", threshold=0.8, target_parameter="inference_enabled"),
        HormoneReceptor("CORTISOL", "CONTINUOUS_MODULATION", gain=0.5, target_parameter="leak_rate"),
    ]
    out = apply_hormone_to_module_params(
        receptors, levels, {"inference_enabled": True, "leak_rate": 1.0, "bypass_safety": False}
    )
    assert out["inference_enabled"] is True and out["leak_rate"] > 1.0 and out["bypass_safety"] is False


def scenario_k4_hormone_shield_reject():
    try:
        apply_hormone_to_module_params(
            [HormoneReceptor("CORTISOL", "BINARY_SWITCH", threshold=0.1, target_parameter="bypass_safety")],
            HormoneLevels(cortisol=1.0),
            {"bypass_safety": False},
        )
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass


def scenario_k5_kill_mirror_fallback():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    bus = HormoneBus(ws, trace=_tr())
    bus.write_telemetry_window(HormoneLevels(cortisol=0.4, window_id="w"))
    bus.kill_mirror()
    reading = bus.read_mirror(consumer="router")
    assert reading.source == "workspace_fallback"
    assert bus.last_diagnosis is not None
    assert bus.last_diagnosis["code"] == "hormone_bus_mirror_killed"


def scenario_k6_replay_high_cortisol_vs_baseline():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    tr = _tr()
    bus = HormoneBus(ws, trace=tr)
    eng = DeterministicEngine()
    reg = RegistryClient(trace=tr)
    c = eng.declare_contract()
    reg.register(c, c.identity.artifact_digest, b"s", module=eng, test_bypass_promote="DELIBERATION")
    bus.write_telemetry_window(HormoneLevels(cortisol=0.1, window_id="base"))
    router = Router(reg, level="L0", trace=tr, hormone_bus=bus)
    plan_lo = router.decide(RouterTask(task_id="lo", form="control_actuation", safety_tier="critical"))
    bus.write_telemetry_window(HormoneLevels(cortisol=0.95, window_id="hi"))
    plan_hi = router.decide(RouterTask(task_id="hi", form="control_actuation", safety_tier="critical"))
    assert plan_lo.disposition == plan_hi.disposition == "DISPATCH"
    routing = [e for e in tr.entries if getattr(e, "form", None) == "control_actuation"]
    assert len(routing) >= 2
    assert routing[-2].rationale["hormone"]["cortisol"] < routing[-1].rationale["hormone"]["cortisol"]


# ── Category L ──────────────────────────────────────────────────────────────


def scenario_l1_danger_surveil():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    immune = ImmuneLayer(ws, trace=_tr())
    antigen = Hypervector.random(seed=42)
    immune._detectors.insert(0, antigen)
    d = immune.ingress(antigen)
    assert d.decision in ("SURVEIL", "QUARANTINE") and ws.read_by_tag(["immune_decision"])


def scenario_l2_pamp_memory_hit():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    immune = ImmuneLayer(ws, trace=_tr())
    antigen = Hypervector.random(seed=123)
    immune._detectors.insert(0, antigen)
    first = immune.ingress(antigen, cortisol=0.0)
    second = immune.ingress(antigen, cortisol=0.0)
    assert first.remembered is False and second.remembered and second.classification == "PAMP"
    assert second.latency_ms <= first.latency_ms + 50.0


def scenario_l3_safe_novelty_low_cortisol():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    immune = ImmuneLayer(ws, trace=_tr())
    self_hv = Hypervector.random(seed=7)
    immune.learn_self(self_hv)
    d = immune.ingress(self_hv, cortisol=0.0)
    assert d.classification in ("SELF", "SAFE") and d.decision in ("PASS", "TOLERATE")


def scenario_l4_high_cortisol_quarantine():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    immune = ImmuneLayer(ws, trace=_tr())
    antigen = Hypervector.random(seed=55)
    immune._detectors.insert(0, antigen)
    assert immune.ingress(antigen, cortisol=0.8).decision == "QUARANTINE"


def scenario_l5_immune_no_deregister():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    immune = ImmuneLayer(ws, trace=_tr())
    try:
        immune.deregister("anything")
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass
    assert immune.direct_lifecycle_calls == 1


def scenario_l6_replay_immune():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    tr = _tr()
    immune = ImmuneLayer(ws, trace=tr)
    antigen = Hypervector.random(seed=3)
    immune._detectors.insert(0, antigen)
    d = immune.ingress(antigen)
    assert ws.read_by_tag(["immune_decision"])[-1].payload["decision"] == d.decision
    assert [e for e in tr.entries if isinstance(e, ImmuneTraceEntry)][-1].decision == d.decision


# ── Category M ──────────────────────────────────────────────────────────────


def scenario_m1_crisis_mode():
    t = [0.0]
    ac = AutonomicController(trace=_tr(), clock=lambda: t[0], config=AutonomicConfig())
    ac.tick(viability=0.1, crisis_precursor=True)
    assert ac.mode == "CRISIS"


def scenario_m2_recovery_hysteresis():
    t = [0.0]
    ac = AutonomicController(
        config=AutonomicConfig(t_down_s=0.05, t_up_s=0.3, t_recovery_dwell_s=0.2),
        clock=lambda: t[0],
    )
    ac.tick(viability=0.1, crisis_precursor=True)
    assert ac.mode == "CRISIS"
    t[0] += 0.01
    ac.tick(viability=0.95, crisis_precursor=False)
    assert ac.mode == "CRISIS"  # single good sample must not flap
    t[0] += 0.25
    ac.tick(viability=0.95)
    if ac.mode == "CRISIS":
        t[0] += 0.3
        ac.tick(viability=0.95)
    assert ac.mode in ("RECOVERY", "PARASYMPATHETIC")


def scenario_m3_autonomic_not_dispatcher():
    ac = AutonomicController()
    try:
        ac.select_module_for_task("task")
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass
    assert ac.select_module_attempts == 1
    eng = DeterministicEngine()
    reg = RegistryClient()
    c = eng.declare_contract()
    reg.register(c, c.identity.artifact_digest, b"s", module=eng, test_bypass_promote="DELIBERATION")
    plan = Router(reg, autonomic_params=RouterExposedParams()).decide(
        RouterTask(task_id="t", form="control_actuation", safety_tier="high")
    )
    assert plan.disposition == "DISPATCH"


def scenario_m4_oscillation_bounded():
    t = [0.0]
    ac = AutonomicController(config=AutonomicConfig(t_down_s=0.1, t_up_s=0.5), clock=lambda: t[0])
    before = len(ac.transitions)
    for i in range(20):
        ac.tick(viability=0.55 if i % 2 == 0 else 0.65, cortisol=0.4)
        t[0] += 0.02
    assert len(ac.transitions) - before <= 2


# ── Category N ──────────────────────────────────────────────────────────────


def scenario_n1_self_terminate_successor_exploration():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    svc = ApoptosisService(ws, trace=_tr())
    c2 = _t2_contract("n1_t2")
    result = svc.begin_self_terminate(
        c2,
        cause="entropy_collapse",
        memory=MemoryExport({"w": 1}, [{"id": 1}], ["entropy_collapse"], {"ece": 0.01}),
        successor_available=True,
        control_affecting=False,
        successor_spec={"mode": "EXPLORATION", "successor_id": "n1_t2__successor", "inherit_memory": True},
    )
    assert result.accepted and result.state == "SUCCEEDED" and result.death_certificate
    assert svc.current_state("n1_t2__successor") == "EXPLORATION"
    assert ws.read_by_tag(["death_certificate"])


def scenario_n2_t0_reject():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    svc = ApoptosisService(ws)
    c = DeterministicEngine().declare_contract()
    c2 = replace(c, lifecycle=replace(c.lifecycle, self_termination_permitted=True))
    r = svc.begin_self_terminate(
        c2, cause="x", memory=MemoryExport({}, [], [], {}), successor_available=True, control_affecting=False
    )
    assert not r.accepted and r.reason == "AP-2"


def scenario_n3_control_no_successor_degraded():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    svc = ApoptosisService(ws)
    c2 = _t2_contract("ctrl_t2")
    result = svc.begin_self_terminate(
        c2,
        cause="staleness",
        memory=MemoryExport({}, [], [], {}),
        successor_available=False,
        control_affecting=True,
    )
    assert not result.accepted and result.state == "DEGRADED" and result.reason == "AP-3"


def scenario_n4_drain_killed_mid_export():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    svc = ApoptosisService(ws, trace=_tr())
    c2 = _t2_contract("n4_t2")
    result = svc.begin_self_terminate(
        c2,
        cause="entropy_collapse",
        memory=MemoryExport({"w": 1}, [{"id": 1}], ["x"], {}),
        successor_available=True,
        control_affecting=False,
        drain_killed_mid_export=True,
    )
    assert not result.accepted
    assert result.state == "SELF_TERMINATING"
    assert result.drain_outcome == "killed"
    assert result.synthetic_lifecycle_recorded
    assert svc.current_state("n4_t2") == "SELF_TERMINATING"
    assert ws.read_by_tag(["lifecycle_synthetic"])
    # No silent SUCCEEDED
    assert result.state != "SUCCEEDED"


def scenario_n5_shadow_validate_blocks_promotion():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    svc = ApoptosisService(ws, trace=_tr())
    c2 = _t2_contract("n5_t2")
    result = svc.begin_self_terminate(
        c2,
        cause="entropy_collapse",
        memory=MemoryExport({"w": 1}, [{"id": 1}, {"id": 2}], ["entropy"], {"ece": 0.01}),
        successor_available=True,
        control_affecting=True,
        successor_spec={"mode": "EXPLORATION", "successor_id": "n5_succ", "inherit_memory": True},
    )
    assert result.accepted and result.state == "SUCCEEDED"
    sv = svc.shadow_validate_successor(
        "n5_succ", "n5_t2", pass_rate=0.2, decisions=[{"id": 99}]
    )
    assert not sv.passed and sv.promotion_blocked
    promo = svc.promote_successor("n5_succ")
    assert not promo.promoted and promo.reason == "promotion_blocked"
    # Pass path then promote
    sv2 = svc.shadow_validate_successor(
        "n5_succ", "n5_t2", pass_rate=0.95, decisions=[{"id": 1}, {"id": 2}]
    )
    assert sv2.passed and not sv2.promotion_blocked
    promo2 = svc.promote_successor("n5_succ")
    assert promo2.promoted and promo2.state == "DELIBERATION"


# ── Category O ──────────────────────────────────────────────────────────────


def scenario_o1_stage_fail():
    tr = MorphogenesisTracker()
    g = DevelopmentalGenome(
        "g",
        [
            DevelopmentalStage(1, "a", locus="a"),
            DevelopmentalStage(2, "b", locus="b"),
            DevelopmentalStage(3, "c", locus="c"),
        ],
    )
    tr.register_genome("m", g)
    tr.run_stage("m", pass_stage=True)
    tr.run_stage("m", pass_stage=True)
    tr.run_stage("m", pass_stage=False)
    assert g.stages[0].status == "PASSED" and g.mutation_locus == "c"


def scenario_o2_development_control_held():
    tr = MorphogenesisTracker()
    g = DevelopmentalGenome("g2", [DevelopmentalStage(1, "a", locus="a")])
    tr.register_genome("baby", g)
    offer = tr.offer_control_actuation("baby")
    assert offer["held"] and not offer["accepted"]
    assert tr.exploration_restrictions_apply("baby")


def scenario_o3_leave_development():
    tr = MorphogenesisTracker()
    g = DevelopmentalGenome(
        "g3",
        [DevelopmentalStage(1, "a", locus="a"), DevelopmentalStage(2, "b", locus="b")],
    )
    tr.register_genome("grown", g)
    assert not tr.leave_development("grown")
    tr.run_stage("grown", pass_stage=True)
    tr.run_stage("grown", pass_stage=True)
    assert tr.leave_development("grown") and tr.may_enter_deliberation("grown")


def scenario_o4_circadian_crisis():
    clock = CircadianClock(rest_start=0.0, rest_end=1.0)
    st = clock.advance(0.0, crisis=True)
    assert st.melatonin_baseline == 0.0 and not st.in_rest


def scenario_o5_kleiber_inefficiency():
    share = kleiber_declared_share(10.0, beta=0.75)
    assert metabolic_inefficiency(share * 2.0, share)
    assert not metabolic_inefficiency(share, share)


# ── Stubs / gates (priorities 3–6) ───────────────────────────────────────────


def scenario_learned_ise_promotion_gate():
    learned = LearnedISE()
    h = HealthVector(thermal=0.8, energy=0.9)
    learned.update(h, 0.85)
    try:
        learned.estimate(h, for_control=True)
        raise AssertionError("control path must be blocked pre-promotion")
    except PermissionError:
        pass
    gate = learned.record_shadow_validate(pass_rate=0.5, ece_ok=False)
    assert not gate.ready() and not learned.promote()
    learned.record_shadow_validate(pass_rate=0.97, ece_ok=True)
    assert learned.promote() and learned.control_path_active
    st = learned.estimate(h, for_control=True)
    assert "learned" in st.model_version


def scenario_federated_oxytocin_fail_closed():
    gate = FederationGate(WorkspaceClient(write_tags=("*",), read_tags=("*",)))
    try:
        gate.federated_oxytocin_release(adapter_acceptance_rate=0.9, peer_nodes=["node-b"])
        raise AssertionError("expected FederationUnsupported")
    except FederationUnsupported as exc:
        assert exc.kind == "FEDERATED_OXYTOCIN"
    assert gate.events and gate.events[-1].kind == "FEDERATED_OXYTOCIN"
    assert not gate.is_distributed_supported()


def scenario_multi_node_mirror_lag_oos():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    bus = HormoneBus(ws)
    gate = FederationGate(ws)
    try:
        gate.simulate_multi_node_mirror_lag(bus, peer_count=3, lag_ms=50.0)
        raise AssertionError("expected FederationUnsupported")
    except FederationUnsupported as exc:
        assert exc.kind == "MULTI_NODE_MIRROR_LAG"
    assert any(e.kind == "MULTI_NODE_MIRROR_LAG" for e in gate.events)


def scenario_metamodel_reproductive_disabled():
    tracker = MetamodelTracker()
    assert not tracker.reproductive_path_enabled()
    try:
        tracker.synthesize({"substrate": "spectral", "device_class": "x"})
        raise AssertionError("expected MetamodelDisabled")
    except MetamodelDisabled:
        pass
    assert tracker.attempts and tracker.attempts[-1]["accepted"] is False


SCENARIOS = {
    "J1": scenario_j1_ise_crisis_precursor,
    "J2": scenario_j2_ise_offline_fallback,
    "J3": scenario_j3_replay_interoceptive,
    "J4": scenario_j4_false_high_probe,
    "K1": scenario_k1_cortisol_release,
    "K2": scenario_k2_staleness_trace,
    "K3": scenario_k3_cortisol_modulation_shield,
    "K4": scenario_k4_hormone_shield_reject,
    "K5": scenario_k5_kill_mirror_fallback,
    "K6": scenario_k6_replay_high_cortisol_vs_baseline,
    "L1": scenario_l1_danger_surveil,
    "L2": scenario_l2_pamp_memory_hit,
    "L3": scenario_l3_safe_novelty_low_cortisol,
    "L4": scenario_l4_high_cortisol_quarantine,
    "L5": scenario_l5_immune_no_deregister,
    "L6": scenario_l6_replay_immune,
    "M1": scenario_m1_crisis_mode,
    "M2": scenario_m2_recovery_hysteresis,
    "M3": scenario_m3_autonomic_not_dispatcher,
    "M4": scenario_m4_oscillation_bounded,
    "N1": scenario_n1_self_terminate_successor_exploration,
    "N2": scenario_n2_t0_reject,
    "N3": scenario_n3_control_no_successor_degraded,
    "N4": scenario_n4_drain_killed_mid_export,
    "N5": scenario_n5_shadow_validate_blocks_promotion,
    "O1": scenario_o1_stage_fail,
    "O2": scenario_o2_development_control_held,
    "O3": scenario_o3_leave_development,
    "O4": scenario_o4_circadian_crisis,
    "O5": scenario_o5_kleiber_inefficiency,
    "LEARNED_ISE": scenario_learned_ise_promotion_gate,
    "FED_OXYTOCIN": scenario_federated_oxytocin_fail_closed,
    "MIRROR_LAG_OOS": scenario_multi_node_mirror_lag_oos,
    "METAMODEL_OOS": scenario_metamodel_reproductive_disabled,
}
