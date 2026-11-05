"""K2 (gaps D1, D2): eligibility mask with typed exclusions, canonical plan bytes, policy digest, trace identity."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from organism_sdk.canonical import canonical_bytes
from organism_sdk.contract import ModuleRole, ReliabilityTier
from organism_sdk.registry import ModuleHandle, RegistryClient
from organism_sdk.router import (
    BOOTSTRAP_POLICY_ID,
    DEFAULT_FORM_TO_ROLES,
    EXCLUSION_CODES,
    DispatchPlan,
    Excluded,
    Router,
    RouterPolicyArtifact,
    RouterTask,
    canonical_routing_entry,
    compute_policy_digest,
    default_bootstrap_policy,
    eligibility,
)


class _Sink:
    """Stands in for TraceEmitter: the router only calls emit_routing."""

    def __init__(self) -> None:
        self.routing: list[object] = []

    def emit_routing(self, entry: object) -> None:
        self.routing.append(entry)


def _h(
    module_id: str,
    role: ModuleRole = ModuleRole.PERCEPTION,
    tier: ReliabilityTier = ReliabilityTier.T0_DETERMINISTIC,
    hardware: str = "NONE",
) -> ModuleHandle:
    return ModuleHandle(
        module_id=module_id,
        version="1.0.0",
        role=role,
        tier=tier,
        state="DELIBERATION",
        contract_digest=b"\x00" * 32,
        hardware_requirement=hardware,
    )


def _mask(handles, *, form="pattern_recognition", tier="medium", level="L0", health=None,
          hardware=None, interpretability=False):
    task = RouterTask(
        task_id="t1", form=form, safety_tier=tier, requires_interpretability=interpretability
    )
    return eligibility(
        handles,
        roles=DEFAULT_FORM_TO_ROLES[form],
        task=task,
        level=level,
        health=health or {},
        available_hardware=hardware or {"NONE"},
    )


def test_every_exclusion_code_is_accepted_and_others_are_refused() -> None:
    for code in EXCLUSION_CODES:
        assert Excluded("m", code).reason_code == code  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown exclusion code"):
        Excluded("m", "not_a_code")  # type: ignore[arg-type]


def test_each_failed_check_gives_its_own_typed_exclusion() -> None:
    handles = [
        _h("ok"),
        _h("wrong_role", role=ModuleRole.SOLVER),
        _h("failed"),
        _h("needs_gpu", hardware="GPU"),
        _h("learned_tier", tier=ReliabilityTier.T2_LEARNED_CALIBRATED),
    ]
    m = _mask(handles, health={"failed": "FAILED"})
    assert [h.module_id for h in m.eligible] == ["ok", "learned_tier"]
    got = {e.module_id: (e.reason_code, dict(e.reason_params)) for e in m.excluded}
    assert got == {
        "wrong_role": ("role_mismatch", {"role": "SOLVER"}),
        "failed": ("health_failed", {}),
        "needs_gpu": ("hardware_capability_missing", {"required": "GPU", "available": "NONE"}),
    }


def test_level_and_tier_exclusions() -> None:
    # L3 allows only MEMORY and GOVERNANCE, so a PERCEPTION module in a PERCEPTION form is level_ineligible.
    m = _mask([_h("p")], level="L3")
    assert m.excluded[0].reason_code == "level_ineligible"
    assert dict(m.excluded[0].reason_params) == {"level": "L3"}
    # Critical allows only T0 and T1, so a learned module is a tier_ineligible.
    m = _mask([_h("learned", tier=ReliabilityTier.T2_LEARNED_CALIBRATED)], tier="critical")
    assert m.excluded[0].reason_code == "tier_ineligible"
    assert dict(m.excluded[0].reason_params) == {"tier": "T2_LEARNED_CALIBRATED"}


def test_l4_admits_only_the_deterministic_engine() -> None:
    gov = _h("governance_other", role=ModuleRole.GOVERNANCE)
    det = _h("deterministic_engine", role=ModuleRole.GOVERNANCE)
    m = _mask([gov, det], form="control_actuation", tier="high", level="L4")
    assert [h.module_id for h in m.eligible] == ["deterministic_engine"]
    assert [e.reason_code for e in m.excluded] == ["l4_deterministic_only"]


def test_interpretability_excludes_learned_tiers() -> None:
    m = _mask([_h("learned", tier=ReliabilityTier.T3_LEARNED_UNCALIBRATED)], interpretability=True)
    assert [e.reason_code for e in m.excluded] == ["interpretability_required"]


def test_mask_is_pure_and_keeps_registry_order() -> None:
    handles = [_h("b"), _h("a"), _h("c", role=ModuleRole.SOLVER)]
    assert _mask(handles) == _mask(handles)
    assert [h.module_id for h in _mask(handles).eligible] == ["b", "a"]


def test_plan_bytes_are_canonical_and_ignore_plan_id() -> None:
    primary = _h("p")
    plan = DispatchPlan(
        plan_id="random-1",
        task_id="t1",
        policy_id=BOOTSTRAP_POLICY_ID,
        policy_digest=b"\x01" * 32,
        level="L0",
        plan_type="DispatchPlan",
        primary=primary,
        fallbacks=[],
        constraints_applied=["level:L0", "form:pattern_recognition"],
        excluded=[Excluded("x", "role_mismatch", {"role": "SOLVER"})],
        ranking_trace=["order=['p']"],
        cross_check_required=False,
        cross_check_module=None,
        justification_required="NONE",
        candidate_roles=["PERCEPTION", "PREDICTION"],
    )
    raw = plan.to_canonical_bytes()
    assert raw == canonical_bytes(json.loads(raw))  # a canonical document decodes and re-encodes to itself
    assert b" " not in raw
    other = replace(plan, plan_id="random-2")
    assert other.to_canonical_bytes() == raw


def test_policy_digest_binds_id_version_and_mapping() -> None:
    base = compute_policy_digest("p", "1", DEFAULT_FORM_TO_ROLES)
    assert base != compute_policy_digest("q", "1", DEFAULT_FORM_TO_ROLES)
    assert base != compute_policy_digest("p", "2", DEFAULT_FORM_TO_ROLES)
    changed = dict(DEFAULT_FORM_TO_ROLES, retrieval=("VERIFIER",))
    assert base != compute_policy_digest("p", "1", changed)
    assert default_bootstrap_policy().digest_matches()


def test_policy_whose_content_does_not_match_its_digest_is_held() -> None:
    tampered = RouterPolicyArtifact(
        policy_id=BOOTSTRAP_POLICY_ID,
        version="0.1.0",
        digest=b"\x00" * 32,
        lifecycle_state="DELIBERATION",
    )
    assert not tampered.digest_matches()
    sink = _Sink()
    plan = Router(RegistryClient(), tampered, trace=sink).decide(  # type: ignore[arg-type]
        RouterTask(task_id="t1", form="pattern_recognition", safety_tier="medium")
    )
    assert plan.disposition == "HOLD"
    assert plan.hold_reason == "policy_digest_mismatch"


def test_routing_trace_entry_carries_policy_identity() -> None:
    sink = _Sink()
    router = Router(RegistryClient(), default_bootstrap_policy(), trace=sink)  # type: ignore[arg-type]
    plan = router.decide(RouterTask(task_id="t1", form="pattern_recognition", safety_tier="medium"))
    assert plan.disposition == "HOLD"
    entry = sink.routing[-1]
    assert entry.policy_id == BOOTSTRAP_POLICY_ID  # type: ignore[attr-defined]
    assert entry.level == "L0"  # type: ignore[attr-defined]
    body = json.loads(canonical_routing_entry(entry))  # type: ignore[arg-type]
    assert body["policy_digest"] == default_bootstrap_policy().digest.hex()
    assert body["hold_reason"] == "no_eligible_candidates"
    assert canonical_routing_entry(entry) == canonical_bytes(body)  # type: ignore[arg-type]
