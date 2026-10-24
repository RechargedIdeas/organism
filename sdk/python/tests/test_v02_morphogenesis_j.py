"""Artifact J / Category O — Circadian, morphogenesis, metabolism."""
from __future__ import annotations

from organism_sdk.autonomic import AutonomicController, RouterExposedParams
from organism_sdk.circadian import CircadianClock, kleiber_declared_share, metabolic_inefficiency
from organism_sdk.morphogenesis import DevelopmentalGenome, DevelopmentalStage, MorphogenesisTracker
from organism_sdk.trace import TraceEmitter, V02TraceSink


def test_o1_stage_fail_retains_prior():
    tr = MorphogenesisTracker()
    g = DevelopmentalGenome("g1", [DevelopmentalStage(1, "scaffold", locus="s1"), DevelopmentalStage(2, "wiring", locus="s2"), DevelopmentalStage(3, "calibrate", locus="s3")])
    tr.register_genome("dev_mod", g)
    tr.run_stage("dev_mod", pass_stage=True); tr.run_stage("dev_mod", pass_stage=True)
    failed = tr.run_stage("dev_mod", pass_stage=False)
    assert failed.status == "FAILED" and g.stages[0].status == "PASSED" and g.stages[1].status == "PASSED" and g.mutation_locus == "s3"


def test_o2_development_blocks_deliberation_and_control():
    tr = MorphogenesisTracker()
    g = DevelopmentalGenome("g2", [DevelopmentalStage(1, "a", locus="a")])
    tr.register_genome("baby", g)
    assert tr.exploration_restrictions_apply("baby") and not tr.may_enter_deliberation("baby")
    tr.run_stage("baby", pass_stage=True)
    assert tr.may_enter_deliberation("baby") and not tr.exploration_restrictions_apply("baby")


def test_o4_circadian_rest_suppressed_in_crisis_and_gates_exploration():
    clock = CircadianClock(rest_start=0.0, rest_end=1.0)
    st = clock.advance(0.0, crisis=False)
    assert st.in_rest and st.melatonin_baseline > 0.5
    gated = clock.apply_to_autonomic_params(RouterExposedParams(exploration_budget=1.0).as_dict(), st)
    assert gated["exploration_budget"] < 0.2 and gated["circadian_in_rest"]
    st2 = clock.advance(0.0, crisis=True)
    assert not st2.in_rest and st2.melatonin_baseline == 0.0


def test_o5_metabolic_kleiber_inefficiency_flag():
    share = kleiber_declared_share(10.0, beta=0.75)
    assert abs(share - (10.0 ** 0.75)) < 1e-9
    assert metabolic_inefficiency(share * 2.0, share) and not metabolic_inefficiency(share, share)


def test_circadian_to_autonomic_auditable():
    tr = TraceEmitter(); tr.attach_v02_sink(V02TraceSink())
    ac = AutonomicController(trace=tr)
    clock = CircadianClock(rest_start=0.0, rest_end=1.0)
    st = clock.advance(0.0)
    params = clock.apply_to_autonomic_params(ac.params.as_dict(), st)
    assert "circadian_phase" in params and params["exploration_budget"] <= 1.0
