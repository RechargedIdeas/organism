"""Bio-digital Hybrid → Organism mapping invariants (v1.1)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from organism_sdk.contract import DataType, MaxSafetyTier, Modality, Severity
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.module import run_handle
from organism_sdk.registry import RegistryClient
from organism_sdk.router import Router, RouterTask, default_bootstrap_policy
from organism_sdk.workspace import WorkspaceClient
from organism_sdk.hormone import HormoneBus, HORMONE_STATE_TAG
from deterministic_engine.engine import DeterministicEngine

from bio_digital.slime_mold import SlimeMoldModule, MODULE_ID as SLIME_ID
from bio_digital.mycelium import MyceliumModule, MODULE_ID as MYCELIUM_ID
from bio_digital.hal import BioDigitalHAL, research_sim_enabled, RUNTIME_RESEARCH_SIM
from bio_digital.limits import PHYSARUM_LIMITS, MYCELIUM_LIMITS
from bio_digital.bus_adapter import BioDigitalBusAdapter, ClusterMessageView
from bio_digital.twin_bridge import TwinBridge, BIO_TWIN_TAG
from bio_digital.hypervisor_map import DrainPolicy, HypervisorMapper


def _perception(form: str, data: bytes = b"\x01\x00") -> PerceptionInput:
    ws = WorkspaceClient()
    return PerceptionInput(
        modalities={
            Modality.PHYSICAL_SENSOR: ModalityPayload(
                modality=Modality.PHYSICAL_SENSOR,
                shape=(1,),
                dtype=DataType.FP32,
                data=b"\x00\x00\x00\x00",
            ),
            Modality.DENSE_VECTOR: ModalityPayload(
                modality=Modality.DENSE_VECTOR,
                shape=(len(data),),
                dtype=DataType.FP32,
                data=data,
            ),
        },
        task_descriptor=TaskDescriptor(
            task_id="bio-t",
            form=form,
            safety_tier="research",
            deadline_ms=500,
            submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=400.0,
        required_modalities=(Modality.PHYSICAL_SENSOR,),
    )


def test_research_sim_default_on(monkeypatch):
    monkeypatch.delenv("ORGANISM_BIO_DIGITAL_SIM", raising=False)
    assert research_sim_enabled()
    hal = BioDigitalHAL(PHYSARUM_LIMITS)
    assert hal.runtime_id == RUNTIME_RESEARCH_SIM


def test_slime_contract_research_only():
    mod = SlimeMoldModule()
    c = mod.declare_contract()
    assert c.safety.may_actuate is False
    assert c.safety.max_safety_tier == MaxSafetyTier.RESEARCH
    assert c.metabolic.requires_special_hardware.value == "PHYSICAL_SUBSTRATE"
    assert not [i for i in c.validate() if i.severity == Severity.ERROR]
    assert any(ch.channel_id.startswith("bio_digital.ipc.") for ch in c.channels)


def test_mycelium_contract_research_only():
    mod = MyceliumModule()
    c = mod.declare_contract()
    assert c.safety.may_actuate is False
    assert c.safety.max_safety_tier == MaxSafetyTier.RESEARCH
    assert not [i for i in c.validate() if i.severity == Severity.ERROR]


@pytest.mark.parametrize("factory", [SlimeMoldModule, MyceliumModule])
def test_bio_refuses_control_actuation(factory):
    mod = factory()
    em = run_handle(mod, _perception("control_actuation"))
    assert em.action_class == "hold"
    body = json.loads(em.payload.decode())
    assert body["refused"] is True
    assert body["reason"] == "bio_digital_never_control_path"


@pytest.mark.parametrize("factory", [SlimeMoldModule, MyceliumModule])
def test_bio_exploration_ok(factory):
    mod = factory()
    em = run_handle(mod, _perception("exploration", data=b"\x01\x01\x80"))
    body = json.loads(em.payload.decode())
    assert body["exploration_only"] is True
    assert "twin" in body


def test_hal_voltage_clamp():
    hal = BioDigitalHAL(PHYSARUM_LIMITS)
    with pytest.raises(ValueError, match="Hardware Trap"):
        hal.apply_potential("E0", PHYSARUM_LIMITS.max_voltage + 0.1)


def test_bus_heartbeat_channel_only_no_workspace_result():
    ws = WorkspaceClient()
    bus = BioDigitalBusAdapter(workspace=ws)
    before = len(ws.read_by_tag(["bio_slime_result"]))
    r = bus.route(
        ClusterMessageView(
            message_id="m1",
            source_node="a",
            target_node="b",
            payload_type="HEARTBEAT",
            data=[1.0],
        )
    )
    assert r.channel_id == "bio_digital.ipc.heartbeat"
    assert r.workspace_binding_id is None
    assert len(ws.read_by_tag(["bio_slime_result"])) == before


def test_bus_spike_train_writes_workspace():
    ws = WorkspaceClient()
    bus = BioDigitalBusAdapter(workspace=ws)
    r = bus.route(
        ClusterMessageView(
            message_id="m2",
            source_node="myc",
            target_node="slime",
            payload_type="SPIKE_TRAIN",
            data=[1.0, 0.0],
        )
    )
    assert r.channel_id == "bio_digital.ipc.spike_train"
    assert r.workspace_binding_id is not None
    bindings = ws.read_by_tag(["bio_slime_result"])
    assert bindings
    assert bindings[0].payload["exploration_only"] is True
    assert bindings[0].affects_control is False
    assert r.result == 1.0  # XOR(1,0)


def test_bus_spatial_graph_writes_workspace():
    ws = WorkspaceClient()
    bus = BioDigitalBusAdapter(workspace=ws)
    r = bus.route(
        ClusterMessageView(
            message_id="m3",
            source_node="slime",
            target_node="myc",
            payload_type="SPATIAL_GRAPH",
            data=[0.4, 0.1, 0.5],
        )
    )
    assert r.workspace_binding_id is not None
    bindings = ws.read_by_tag(["bio_mycelium_result"])
    assert bindings
    assert bindings[0].module_id == MYCELIUM_ID


def test_twin_bridge_to_workspace_and_hormone():
    ws = WorkspaceClient()
    hormone = HormoneBus(ws)
    bridge = TwinBridge(workspace=ws, hormone=hormone)
    hal = BioDigitalHAL(MYCELIUM_LIMITS, node_id="m0")
    # Unhealthy → stress feed
    hal.set_environment(temp_c=40.0, humidity_pct=10.0)
    tw = bridge.publish(hal, module_id=MYCELIUM_ID, feed_hormone=True)
    assert tw.stress > 0
    twins = ws.read_by_tag([BIO_TWIN_TAG])
    assert twins
    assert twins[0].affects_control is False
    hormones = ws.read_by_tag([HORMONE_STATE_TAG])
    assert hormones
    assert hormones[0].payload["cortisol"] > 0


def test_hypervisor_hot_swap_after_drain():
    reg = RegistryClient()
    active = SlimeMoldModule(node_id="active")
    standby = SlimeMoldModule(node_id="standby")
    ca = active.declare_contract()
    # Distinct module ids for roles
    # register under distinct ids by mutating identity via fresh modules with patched ids
    # Use contract module_id as-is for active; for standby register a second entry by
    # temporarily changing MODULE path — simpler: hot_swap on single registered module.
    reg.register(
        ca,
        artifact_digest=ca.identity.artifact_digest,
        author_signature=b"s",
        module=active,
        test_bypass_promote="DELIBERATION",
    )
    mapper = HypervisorMapper(reg, drain=DrainPolicy(drain_timeout_s=0.01))
    mapper.bind_roles(active_id=SLIME_ID, standby_id="bio_digital.slime_mold.standby")
    result = mapper.failover_active_to_standby(active_module=active)
    assert result.accepted is True
    assert result.reason == "hot_swap"
    assert result.active_id == "bio_digital.slime_mold.standby"


def test_router_excludes_bio_without_physical_hw():
    reg = RegistryClient()
    slime = SlimeMoldModule()
    c = slime.declare_contract()
    reg.register(
        c,
        artifact_digest=c.identity.artifact_digest,
        author_signature=b"s",
        module=slime,
        test_bypass_promote="DELIBERATION",
    )
    eng = DeterministicEngine()
    ce = eng.declare_contract()
    reg.register(
        ce,
        artifact_digest=ce.identity.artifact_digest,
        author_signature=b"s",
        module=eng,
        test_bypass_promote="DELIBERATION",
    )
    router = Router(
        reg,
        default_bootstrap_policy(),
        level="L0",
        plan_id_factory=lambda: "p",
        available_hardware={"NONE"},
    )
    plan = router.decide(
        RouterTask(task_id="t", form="control_actuation", safety_tier="high")
    )
    # Bio module must not be primary on control_actuation
    assert (plan.primary.module_id if plan.primary else None) != SLIME_ID
    # And slime itself refuses even if somehow asked
    em = run_handle(slime, _perception("control_actuation"))
    assert json.loads(em.payload.decode())["refused"] is True


def test_router_excludes_bio_hardware_gate():
    reg = RegistryClient()
    slime = SlimeMoldModule()
    c = slime.declare_contract()
    reg.register(
        c,
        artifact_digest=c.identity.artifact_digest,
        author_signature=b"s",
        module=slime,
        test_bypass_promote="DELIBERATION",
    )
    eng = DeterministicEngine()
    ce = eng.declare_contract()
    reg.register(
        ce,
        artifact_digest=ce.identity.artifact_digest,
        author_signature=b"s",
        module=eng,
        test_bypass_promote="DELIBERATION",
    )
    router = Router(
        reg,
        default_bootstrap_policy(),
        level="L0",
        plan_id_factory=lambda: "p",
        available_hardware={"NONE"},
    )
    plan = router.decide(
        RouterTask(task_id="t2", form="exploration", safety_tier="research")
    )
    excl = [e for e in plan.excluded if e.module_id == SLIME_ID]
    primary_id = plan.primary.module_id if plan.primary else None
    assert primary_id != SLIME_ID or (
        excl and excl[0].reason_code == "hardware_capability_missing"
    )
