"""M3: form mapping, tier lattice, level gating, router determinism."""
from __future__ import annotations

from deterministic_engine.engine import DeterministicEngine
from organism_sdk.registry import RegistryClient
from organism_sdk.router import Router, RouterTask, default_bootstrap_policy
from organism_sdk.trace import TraceEmitter


def _reg_with_engine():
    eng = DeterministicEngine()
    reg = RegistryClient()
    c = eng.declare_contract()
    reg.register(
        c,
        artifact_digest=c.identity.artifact_digest,
        author_signature=b"s",
        module=eng,
        test_bypass_promote="DELIBERATION",
    )
    return reg, eng


def test_form_mapping_control_actuation_to_t0():
    reg, _ = _reg_with_engine()
    policy = default_bootstrap_policy()
    router = Router(reg, policy, level="L0", plan_id_factory=lambda: "plan-fixed")
    plan = router.decide(
        RouterTask(task_id="t1", form="control_actuation", safety_tier="high")
    )
    assert plan.disposition == "DISPATCH"
    assert plan.plan_type == "DispatchPlan"
    assert plan.primary is not None
    assert plan.primary.module_id == "deterministic_engine"
    assert plan.cross_check_required is False  # T0 proposer


def test_tier_lattice_critical_forbids_learned_only_t0_ok():
    reg, _ = _reg_with_engine()
    router = Router(reg, level="L0", plan_id_factory=lambda: "p")
    plan = router.decide(
        RouterTask(task_id="t2", form="control_actuation", safety_tier="critical")
    )
    assert plan.primary is not None
    assert plan.primary.tier.value == "T0_DETERMINISTIC"


def test_level_gating_l3_never_dispatch_plan():
    reg, _ = _reg_with_engine()
    router = Router(reg, level="L3", plan_id_factory=lambda: "p")
    plan = router.decide(
        RouterTask(task_id="t3", form="control_actuation", safety_tier="high")
    )
    assert plan.plan_type == "DegradedDispatchPlan"
    # L3 eligible roles include GOVERNANCE — may dispatch engine
    assert plan.disposition in ("DISPATCH", "HOLD")


def test_level_gating_l4_deterministic_only():
    reg, _ = _reg_with_engine()
    router = Router(reg, level="L4", plan_id_factory=lambda: "p")
    plan = router.decide(
        RouterTask(task_id="t4", form="control_actuation", safety_tier="high")
    )
    assert plan.plan_type == "DegradedDispatchPlan"
    assert plan.disposition == "DISPATCH"
    assert plan.primary.module_id == "deterministic_engine"


def test_router_determinism_byte_identical():
    reg, _ = _reg_with_engine()
    policy = default_bootstrap_policy()
    r1 = Router(reg, policy, level="L0", plan_id_factory=lambda: "fixed")
    r2 = Router(reg, policy, level="L0", plan_id_factory=lambda: "fixed")
    task = RouterTask(task_id="td", form="control_actuation", safety_tier="high")
    p1 = r1.decide(task)
    p2 = r2.decide(task)
    assert p1.to_canonical_bytes() == p2.to_canonical_bytes()


def test_pattern_recognition_hold_without_prediction_module():
    reg, _ = _reg_with_engine()
    router = Router(reg, level="L0", plan_id_factory=lambda: "p")
    plan = router.decide(
        RouterTask(task_id="t5", form="pattern_recognition", safety_tier="medium")
    )
    # Only GOVERNANCE registered — role mismatch → HOLD
    assert plan.disposition == "HOLD"
    assert plan.hold_reason == "no_eligible_candidates"
