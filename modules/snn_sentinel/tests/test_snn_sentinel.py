"""v0.3-M4 — SNN sentinel hardware gate + simulated spike wake."""
from __future__ import annotations

from deterministic_engine.engine import DeterministicEngine
from organism_sdk.registry import CapabilityFilter, RegistryClient
from organism_sdk.router import Router, RouterTask, default_bootstrap_policy
from organism_sdk.workspace import WorkspaceClient
from snn_sentinel.module import MODULE_ID, SPIKE_WAKE_TAG, SNNSentinel


def _register_snn(reg: RegistryClient, snn: SNNSentinel) -> None:
    c = snn.declare_contract()
    reg.register(
        c,
        artifact_digest=c.identity.artifact_digest,
        author_signature=b"s",
        module=snn,
        test_bypass_promote="DELIBERATION",
    )


def _register_engine(reg: RegistryClient) -> None:
    eng = DeterministicEngine()
    c = eng.declare_contract()
    reg.register(
        c,
        artifact_digest=c.identity.artifact_digest,
        author_signature=b"s",
        module=eng,
        test_bypass_promote="DELIBERATION",
    )


def test_snn_registers_with_neuromorphic_requirement():
    reg = RegistryClient()
    snn = SNNSentinel()
    _register_snn(reg, snn)
    handles = reg.query(CapabilityFilter(min_lifecycle_state="DELIBERATION"))
    h = next(x for x in handles if x.module_id == MODULE_ID)
    assert h.hardware_requirement == "NEUROMORPHIC"
    assert h.role.value == "SENTINEL"


def test_no_dispatch_without_neuromorphic_hardware():
    reg = RegistryClient()
    _register_engine(reg)
    _register_snn(reg, SNNSentinel())
    router = Router(
        reg,
        default_bootstrap_policy(),
        level="L0",
        plan_id_factory=lambda: "p",
        available_hardware={"NONE"},  # box default
    )
    plan = router.decide(
        RouterTask(task_id="t1", form="anomaly_detection", safety_tier="medium")
    )
    # SNN must be excluded; may HOLD or dispatch another eligible module
    snn_excl = [e for e in plan.excluded if e.module_id == MODULE_ID]
    assert snn_excl
    assert snn_excl[0].reason_code == "hardware_capability_missing"
    if plan.primary is not None:
        assert plan.primary.module_id != MODULE_ID


def test_dispatch_allowed_when_neuromorphic_present():
    reg = RegistryClient()
    _register_snn(reg, SNNSentinel(hardware_present=True))
    router = Router(
        reg,
        default_bootstrap_policy(),
        level="L0",
        plan_id_factory=lambda: "p",
        available_hardware={"NONE", "NEUROMORPHIC"},
    )
    plan = router.decide(
        RouterTask(task_id="t2", form="anomaly_detection", safety_tier="medium")
    )
    assert plan.disposition == "DISPATCH"
    assert plan.primary is not None
    assert plan.primary.module_id == MODULE_ID


def test_simulated_spike_wake_escalates_router():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    snn = SNNSentinel(workspace=ws, spike_threshold_hz=50.0)
    reg = RegistryClient()
    _register_engine(reg)
    _register_snn(reg, snn)
    router = Router(reg, level="L0", plan_id_factory=lambda: "p")
    assert router.current_level() == "L0"

    below = snn.simulate_spikes(10.0)
    assert below["wake"] is False
    assert not ws.read_by_tag([SPIKE_WAKE_TAG])

    above = snn.simulate_spikes(120.0)
    assert above["wake"] is True
    wakes = ws.read_by_tag([SPIKE_WAKE_TAG])
    assert wakes
    assert wakes[0].payload["rate_hz"] == 120.0
    assert wakes[0].affects_control is False

    router.escalate_from_sentinel(reason="snn_spike_wake", spike_rate=120.0)
    assert router.current_level() == "L1"
    assert router.autonomic_params.cross_check_frequency >= 2.0
    assert router.last_sentinel_escalation["reason"] == "snn_spike_wake"
