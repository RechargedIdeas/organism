"""v1.2 Category — Bio-digital hypervisor Active/Standby drill."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from organism_sdk.contract import DataType, Modality
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.module import run_handle
from organism_sdk.registry import RegistryClient
from organism_sdk.workspace import WorkspaceClient

from bio_digital.hypervisor_map import DrainPolicy, HypervisorMapper
from bio_digital.slime_mold import MODULE_ID as SLIME_ID, SlimeMoldModule


def run_hypervisor_drill() -> dict:
    reg = RegistryClient()
    active = SlimeMoldModule(node_id="hv-active", backend="stub")
    standby = SlimeMoldModule(node_id="hv-standby", backend="stub")
    ca = active.declare_contract()
    reg.register(
        ca,
        artifact_digest=ca.identity.artifact_digest,
        author_signature=b"s",
        module=active,
        test_bypass_promote="DELIBERATION",
    )
    mapper = HypervisorMapper(reg, drain=DrainPolicy(drain_timeout_s=0.01, abandon_in_flight=True))
    mapper.bind_roles(active_id=SLIME_ID, standby_id="bio_digital.slime_mold.standby")
    mapper.attach_modules(active=active, standby=standby)
    mapper.begin_workload()
    killed = mapper.kill_active_mid_flight(cause="harness_crash")

    ws = WorkspaceClient()
    inp = PerceptionInput(
        modalities={
            Modality.PHYSICAL_SENSOR: ModalityPayload(
                modality=Modality.PHYSICAL_SENSOR,
                shape=(1,),
                dtype=DataType.FP32,
                data=b"\x00",
            ),
        },
        task_descriptor=TaskDescriptor(
            task_id="hv-control",
            form="control_actuation",
            safety_tier="high",
            deadline_ms=100,
            submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=50.0,
        required_modalities=(Modality.PHYSICAL_SENSOR,),
    )
    em = run_handle(standby, inp)
    body = json.loads(em.payload.decode())
    return {
        "accepted": killed.accepted,
        "killed_mid_flight": killed.killed_mid_flight,
        "control_path_used": killed.control_path_used,
        "active_id": killed.active_id,
        "bio_refused_control": body.get("refused") is True,
        "may_actuate": ca.safety.may_actuate,
    }


def test_v12_hypervisor_drill_gate():
    result = run_hypervisor_drill()
    assert result["accepted"] is True
    assert result["killed_mid_flight"] is True
    assert result["control_path_used"] is False
    assert result["bio_refused_control"] is True
    assert result["may_actuate"] is False
