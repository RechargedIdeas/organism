"""Phase 3 — Active/Standby hypervisor drill + kill-active fault injection."""
from __future__ import annotations

import json

from organism_sdk.contract import DataType, MaxSafetyTier, Modality
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.module import run_handle
from organism_sdk.registry import RegistryClient
from organism_sdk.workspace import WorkspaceClient
from datetime import datetime, timezone

from bio_digital.slime_mold import MODULE_ID as SLIME_ID, SlimeMoldModule
from bio_digital.hypervisor_map import DrainPolicy, HypervisorMapper


def _perception(form: str = "exploration") -> PerceptionInput:
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
                shape=(2,),
                dtype=DataType.FP32,
                data=b"\x01\x00",
            ),
        },
        task_descriptor=TaskDescriptor(
            task_id="hv-t",
            form=form,
            safety_tier="research",
            deadline_ms=500,
            submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=400.0,
        required_modalities=(Modality.PHYSICAL_SENSOR,),
    )


def test_drain_hot_swap_promote_e2e():
    reg = RegistryClient()
    active = SlimeMoldModule(node_id="active", backend="stub")
    standby = SlimeMoldModule(node_id="standby", backend="stub")
    ca = active.declare_contract()
    assert ca.safety.may_actuate is False
    reg.register(
        ca,
        artifact_digest=ca.identity.artifact_digest,
        author_signature=b"s",
        module=active,
        test_bypass_promote="DELIBERATION",
    )
    mapper = HypervisorMapper(reg, drain=DrainPolicy(drain_timeout_s=0.01))
    mapper.bind_roles(active_id=SLIME_ID, standby_id="bio_digital.slime_mold.standby")
    mapper.attach_modules(active=active, standby=standby)
    mapper.begin_workload()
    result = mapper.failover_active_to_standby(active_module=active)
    assert result.accepted is True
    assert result.reason == "hot_swap"
    assert result.control_path_used is False
    assert result.active_id == "bio_digital.slime_mold.standby"
    assert mapper.active_slot() is not None
    assert mapper.active_slot().role == "ACTIVE"
    assert mapper.assert_no_control_path()


def test_kill_active_mid_flight_promotes_standby():
    reg = RegistryClient()
    active = SlimeMoldModule(node_id="active-kill", backend="stub")
    standby = SlimeMoldModule(node_id="standby-kill", backend="stub")
    ca = active.declare_contract()
    reg.register(
        ca,
        artifact_digest=ca.identity.artifact_digest,
        author_signature=b"s",
        module=active,
        test_bypass_promote="DELIBERATION",
    )
    mapper = HypervisorMapper(reg, drain=DrainPolicy(drain_timeout_s=0.01, abandon_in_flight=True))
    mapper.bind_roles(
        active_id=SLIME_ID,
        standby_id="bio_digital.slime_mold.standby",
    )
    mapper.attach_modules(active=active, standby=standby)
    mapper.heartbeat(SLIME_ID)
    mapper.begin_workload(SLIME_ID)
    assert mapper.slots[SLIME_ID].in_flight is True

    result = mapper.kill_active_mid_flight(cause="simulated_crash")
    assert result.accepted is True
    assert result.killed_mid_flight is True
    assert result.control_path_used is False
    assert result.active_id == "bio_digital.slime_mold.standby"
    assert mapper.slots[SLIME_ID].alive is False
    assert mapper.slots[SLIME_ID].role == "DEAD"
    assert mapper.active_slot().module_id == "bio_digital.slime_mold.standby"
    assert mapper.active_slot().role == "ACTIVE"

    # Bio modules still refuse control after failover
    em = run_handle(standby, _perception("control_actuation"))
    body = json.loads(em.payload.decode())
    assert body["refused"] is True
    assert body["reason"] == "bio_digital_never_control_path"
    assert standby.declare_contract().safety.max_safety_tier == MaxSafetyTier.RESEARCH


def test_hypervisor_events_never_control():
    reg = RegistryClient()
    active = SlimeMoldModule(backend="stub")
    standby = SlimeMoldModule(node_id="s2", backend="stub")
    ca = active.declare_contract()
    reg.register(
        ca,
        artifact_digest=ca.identity.artifact_digest,
        author_signature=b"s",
        module=active,
        test_bypass_promote="DELIBERATION",
    )
    mapper = HypervisorMapper(reg, drain=DrainPolicy(drain_timeout_s=0.01))
    mapper.bind_roles(active_id=SLIME_ID, standby_id="standby-x")
    mapper.attach_modules(active=active, standby=standby)
    mapper.begin_workload()
    mapper.kill_active_mid_flight()
    assert mapper.assert_no_control_path()
    assert any(e["event"] == "kill_active" for e in mapper.events)
    assert any(e["event"] == "promote" for e in mapper.events)
