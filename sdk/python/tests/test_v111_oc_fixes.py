"""v1.11 OC-1 … OC-13 — Organism fixes proposed by CryptoMiner substrate integration."""
from __future__ import annotations

import sys
from collections import deque
from typing import Any

import pytest
from organism_sdk.contract import (
    Determinism,
    JustificationKind,
    ModuleRole,
    ReliabilityTier,
    Severity,
    SubstrateContract,
    ValidationIssue,
)
from organism_sdk.contract_factory import make_contract
from organism_sdk.degradation import DegradationMachine, DegradationThresholds, HealthSignals
from organism_sdk.lifecycle_trace import validate_lct3, validate_lct12, validate_lifecycle_entry
from organism_sdk.registry import CapabilityFilter, ModuleHandle, RegistryClient
from organism_sdk.router import (
    Router,
    RouterPolicyArtifact,
    RouterTask,
    compute_policy_digest,
    default_bootstrap_policy,
    eligibility,
)
from organism_sdk.sandbox import SandboxPolicy, capabilities
from organism_sdk.sandbox import jail as jail_mod
from organism_sdk.trace import LifecycleTraceEntry, TraceEmitter, V02TraceSink


def _register(
    rc: RegistryClient,
    mid: str,
    *,
    role: ModuleRole = ModuleRole.SOLVER,
    tier: ReliabilityTier = ReliabilityTier.T0_DETERMINISTIC,
    state: str = "DELIBERATION",
    **kw: Any,
) -> SubstrateContract:
    c = make_contract(
        module_id=mid,
        version="0.1.0",
        role=role,
        tier=tier,
        modalities=(),
        required_modalities=(),
        output_form=__import__("organism_sdk.contract", fromlist=["OutputForm"]).OutputForm.SCALAR,
        uncertainty=__import__("organism_sdk.contract", fromlist=["UncertaintyKind"]).UncertaintyKind.NONE,
        determinism=Determinism.DETERMINISTIC,
        justification_kind=JustificationKind.NONE,
        justification_format="",
        required_fields=(),
        **kw,
    )
    rc.register(c, b"\x00" * 32, b"", initial_state=state)  # type: ignore[arg-type]
    return c


# ---- OC-1 ----
def test_oc1_deprecated_modules_are_not_routable() -> None:
    rc = RegistryClient()
    _register(rc, "live", state="DELIBERATION")
    _register(rc, "old", state="DEPRECATED")
    _register(rc, "gone", state="RETIRED")
    ids = {h.module_id for h in rc.query(CapabilityFilter(min_lifecycle_state="DELIBERATION"))}
    assert ids == {"live"}
    # Explicit demotion queries still see demoted modules.
    retired = {h.module_id for h in rc.query(CapabilityFilter(min_lifecycle_state="RETIRED"))}
    assert "gone" in retired


# ---- OC-2 ----
def test_oc2_rollback_emits_rollback_operation_and_link() -> None:
    rc = RegistryClient()
    _register(rc, "m", state="DELIBERATION")
    resp = rc.rollback("m", "SHADOW_VALIDATED", reason="shield", rollback_of_entry_id="promote-1")
    assert resp.accepted
    assert rc.state("m") == "SHADOW_VALIDATED"
    entries = [e for e in rc._trace.entries if getattr(e, "event", "") == "rollback"]
    assert entries
    assert entries[-1].operation == "ROLLBACK"
    assert entries[-1].rollback_of_entry_id == "promote-1"
    assert entries[-1].reason == "shield"


def test_oc2_rollback_rejects_retired() -> None:
    rc = RegistryClient()
    _register(rc, "m", state="RETIRED")
    resp = rc.rollback("m", "DELIBERATION")
    assert not resp.accepted
    assert resp.validation_issues[0].code == "rollback_from_retired"


# ---- OC-3 ----
def test_oc3_l4_admits_declared_terminal_not_just_builtin_id() -> None:
    custom = ModuleHandle(
        module_id="cm_det_strategy",
        version="1.0.0",
        role=ModuleRole.GOVERNANCE,
        tier=ReliabilityTier.T0_DETERMINISTIC,
        state="DELIBERATION",
        contract_digest=b"\x00" * 32,
        l4_terminal=True,
    )
    other = ModuleHandle(
        module_id="governance_other",
        version="1.0.0",
        role=ModuleRole.GOVERNANCE,
        tier=ReliabilityTier.T0_DETERMINISTIC,
        state="DELIBERATION",
        contract_digest=b"\x00" * 32,
        l4_terminal=False,
    )
    task = RouterTask(task_id="t", form="control_actuation", safety_tier="high")
    mask = eligibility(
        [custom, other],
        roles=["ACTUATOR", "GOVERNANCE", "VERIFIER"],
        task=task,
        level="L4",
        health={},
        available_hardware={"NONE"},
    )
    assert [h.module_id for h in mask.eligible] == ["cm_det_strategy"]
    assert mask.excluded[0].reason_code == "l4_deterministic_only"


def test_oc3_l4_terminal_contract_validation() -> None:
    bad = make_contract(
        module_id="bad_l4",
        version="0.1.0",
        role=ModuleRole.SOLVER,  # not GOVERNANCE
        tier=ReliabilityTier.T0_DETERMINISTIC,
        modalities=(),
        required_modalities=(),
        output_form=__import__("organism_sdk.contract", fromlist=["OutputForm"]).OutputForm.SCALAR,
        uncertainty=__import__("organism_sdk.contract", fromlist=["UncertaintyKind"]).UncertaintyKind.NONE,
        determinism=Determinism.DETERMINISTIC,
        justification_kind=JustificationKind.RULE_TRACE,
        justification_format="x",
        required_fields=("a",),
        l4_terminal=True,
    )
    codes = {i.code for i in bad.validate() if i.severity == Severity.ERROR}
    assert "l4_terminal_role" in codes


# ---- OC-4 ----
def test_oc4_health_signals_default_to_empty_neural_lists() -> None:
    s = HealthSignals()
    assert s.neural_modules == ()
    assert s.leading_predictive == ()
    m = DegradationMachine(signals=s)
    m.signals.thermal = 0.05
    m.tick()
    m.advance(5.0)
    # Thermal alone still drives L0→L1; empty neural does not invent a phantom module.
    assert m.level == "L1"


# ---- OC-5 ----
def test_oc5_deny_network_plans_net_namespace_without_full_ns_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORGANISM_JAIL_FULL_NS", raising=False)
    monkeypatch.setattr(
        jail_mod,
        "capabilities",
        lambda: {
            "linux": True,
            "unshare": True,
            "rlimits": True,
            "network_namespace": True,
        },
    )
    flags, attempted, degraded = jail_mod._plan_namespaces(SandboxPolicy(allow_network=False))
    assert "net" in attempted
    assert "user" in attempted
    assert degraded == []
    assert flags & 0x40000000  # CLONE_NEWNET


def test_oc5_require_isolation_refuses_when_host_cannot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        jail_mod,
        "capabilities",
        lambda: {"linux": False, "unshare": False, "rlimits": True, "network_namespace": False},
    )
    policy = SandboxPolicy(
        allow_network=False, isolate_network=True, require_network_isolation=True, use_namespaces=True
    )
    result = jail_mod.ProcessJail(policy).run([sys.executable, "-c", "print(1)"])
    assert not result.ok
    assert result.refused and "network isolation required" in result.refused
    assert "isolation_not_claimed" in result.degraded


def test_oc5_capabilities_report_network_namespace() -> None:
    caps = capabilities()
    assert "network_namespace" in caps
    assert caps["claims_isolation_without_report"] is False


# ---- OC-6 ----
def test_oc6_custom_thermal_thresholds() -> None:
    th = DegradationThresholds(thermal_l1=0.05, thermal_l0=0.10)
    m = DegradationMachine(
        signals=HealthSignals(thermal=0.15, neural_modules=(), leading_predictive=()),
        thresholds=th,
    )
    m.tick()
    m.advance(5.0)
    # 0.15 > thermal_l1=0.05, so no L0→L1 on thermal.
    assert m.level == "L0"
    m.signals.thermal = 0.01
    m.tick()
    m.advance(5.0)
    assert str(m.level) == "L1"


# ---- OC-7 ----
def test_oc7_learned_first_ranking() -> None:
    rc = RegistryClient()
    _register(rc, "t0_solver", role=ModuleRole.SOLVER, tier=ReliabilityTier.T0_DETERMINISTIC)
    _register(rc, "learned", role=ModuleRole.SOLVER, tier=ReliabilityTier.T2_LEARNED_CALIBRATED)
    digest = compute_policy_digest(
        "p", "1", {"constrained_allocation": ("SOLVER",)}, ranking="learned_first_with_t0_fallback"
    )
    policy = RouterPolicyArtifact(
        policy_id="p",
        version="1",
        digest=digest,
        form_to_roles={"constrained_allocation": ("SOLVER",)},
        ranking="learned_first_with_t0_fallback",
    )
    router = Router(rc, policy=policy, level="L0")
    plan = router.decide(RouterTask(task_id="t", form="constrained_allocation", safety_tier="medium"))
    assert plan.disposition == "DISPATCH"
    assert plan.primary is not None and plan.primary.module_id == "learned"
    assert any(f.module_id == "t0_solver" for f in plan.fallbacks)


def test_oc7_ranking_in_policy_digest() -> None:
    a = compute_policy_digest("p", "1", {"x": ("SOLVER",)}, ranking="trust_first")
    b = compute_policy_digest("p", "1", {"x": ("SOLVER",)}, ranking="metabolic")
    assert a != b
    # Bootstrap digest includes ranking=trust_first
    boot = default_bootstrap_policy()
    assert boot.digest_matches()
    assert boot.ranking == "trust_first"


# ---- OC-8 ----
def test_oc8_contract_factory_public_and_modules_packaged() -> None:
    import organism_modules
    from organism_sdk.contract_factory import make_contract as mc

    assert "reservoir" in organism_modules.REFERENCE_MODULES
    c = mc(
        module_id="x",
        version="0.1.0",
        role=ModuleRole.SOLVER,
        tier=ReliabilityTier.T0_DETERMINISTIC,
        modalities=(),
        required_modalities=(),
        output_form=__import__("organism_sdk.contract", fromlist=["OutputForm"]).OutputForm.SCALAR,
        uncertainty=__import__("organism_sdk.contract", fromlist=["UncertaintyKind"]).UncertaintyKind.NONE,
        determinism=Determinism.DETERMINISTIC,
        justification_kind=JustificationKind.NONE,
        justification_format="",
        required_fields=(),
    )
    assert c.identity.module_id == "x"


# ---- OC-9 ----
def test_oc9_public_accessors() -> None:
    rc = RegistryClient()
    _register(rc, "m")
    assert rc.state("m") == "DELIBERATION"
    router = Router(rc)
    router.set_health({"m": "FAILED"})
    router.set_health(n="DEGRADED")
    assert router._health["m"] == "FAILED"
    assert router._health["n"] == "DEGRADED"


# ---- OC-10 / OC-11 ----
def test_oc10_oc11_policy_fields_and_degraded_reasons(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        jail_mod,
        "capabilities",
        lambda: {
            "linux": True,
            "unshare": True,
            "rlimits": True,
            "network_namespace": True,
            "cgroup_cpu_quota": False,
            "cpu_affinity": False,
            "nice": False,
            "seccomp": False,
        },
    )
    policy = SandboxPolicy(
        allow_network=False,
        cpu_quota=0.5,
        cpu_affinity=(0,),
        nice=5,
        seccomp_profile="minimal",
        devices=("/dev/null",),
        use_namespaces=True,
        require_network_isolation=False,
    )
    d = policy.as_dict()
    assert d["cpu_quota"] == 0.5
    assert d["devices"] == ["/dev/null"]
    # Planning alone should not crash; running reports degraded controls.
    result = jail_mod.ProcessJail(policy).run([sys.executable, "-c", "print('hi')"])
    # May or may not succeed depending on unshare; either way OC-10 reasons appear when caps say no.
    for reason in ("cpu_quota_unavailable", "cpu_affinity_unavailable", "nice_unavailable", "seccomp_unavailable", "devices_not_bound"):
        assert reason in result.degraded


# ---- OC-12 ----
def test_oc12_lct3_tolerates_warnings() -> None:
    entry = LifecycleTraceEntry(
        module_id="m",
        from_state="SANDBOXED",
        to_state="SHADOW_VALIDATED",
        event="promote",
        operation="PROMOTE",
        validation_issues=[ValidationIssue(Severity.WARNING, "soft", "x", "warn")],
    )
    assert validate_lct3(entry) == []


def test_oc12_lct12_rollback_link() -> None:
    prior = LifecycleTraceEntry(
        module_id="m",
        from_state="EXPLORATION",
        to_state="DELIBERATION",
        event="promote",
        operation="PROMOTE",
        entry_id="p1",
    )
    ok = LifecycleTraceEntry(
        module_id="m",
        from_state="DELIBERATION",
        to_state="EXPLORATION",
        event="rollback",
        operation="ROLLBACK",
        entry_id="r1",
        rollback_of_entry_id="p1",
    )
    assert validate_lct12(ok, [prior]) == []
    bad = LifecycleTraceEntry(
        module_id="m",
        from_state="DELIBERATION",
        to_state="EXPLORATION",
        event="rollback",
        operation="ROLLBACK",
        rollback_of_entry_id="missing",
    )
    issues = validate_lifecycle_entry(bad, [prior])
    assert any(i.code == "lct12_unknown_rollback_target" for i in issues)


# ---- OC-13 ----
def test_oc13_v02_sink_is_bounded_and_default_attached() -> None:
    sink = V02TraceSink(maxlen=3)
    for i in range(5):
        sink.record(i)
    assert sink.entries == [2, 3, 4]
    assert isinstance(sink._entries, deque)

    tr = TraceEmitter()  # auto-attaches
    assert tr._v02_sink is not None
    from organism_sdk.trace import HormoneTraceEntry

    tr.emit_hormone(HormoneTraceEntry(cortisol=0.1))
    assert len(tr._v02_sink.entries) == 1

    tr2 = TraceEmitter(auto_attach_v02_sink=False)
    tr2.emit_hormone(HormoneTraceEntry(cortisol=0.2))
    assert tr2.v02_missing_diagnoses[-1]["code"] == "v02_sink_missing"
