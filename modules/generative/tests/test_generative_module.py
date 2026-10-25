"""Generative Organism module contract + refuse control + handle evolve forms."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from generative.module import MODULE_ID, MODULE_VERSION, GenerativeOrganismModule
from organism_sdk.contract import DataType, Modality
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.workspace import WorkspaceClient


def test_contract_may_actuate_false():
    mod = GenerativeOrganismModule()
    c = mod.declare_contract()
    assert c.identity.module_id == MODULE_ID
    assert c.safety.may_actuate is False
    assert MODULE_VERSION.startswith("1.9") or MODULE_VERSION.startswith("1.")
    c.validate()


def test_handle_refuses_control_actuation():
    mod = GenerativeOrganismModule()
    ws = WorkspaceClient()
    inp = PerceptionInput(
        modalities={
            Modality.DENSE_VECTOR: ModalityPayload(
                modality=Modality.DENSE_VECTOR, shape=(1,), dtype=DataType.FP32, data=b"\x00\x00\x00\x00"
            )
        },
        task_descriptor=TaskDescriptor(
            task_id="g1",
            form="control_actuation",
            safety_tier="research",
            deadline_ms=500,
            submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=400.0,
        required_modalities=(Modality.DENSE_VECTOR,),
    )
    em = mod.handle(inp)
    assert em.action_class == "hold"
    body = json.loads(em.payload.decode())
    assert body.get("refused") is True


def test_health_and_non_control_handle():
    mod = GenerativeOrganismModule()
    h = mod.health()
    assert h is not None
    ws = WorkspaceClient()
    inp = PerceptionInput(
        modalities={
            Modality.DENSE_VECTOR: ModalityPayload(
                modality=Modality.DENSE_VECTOR, shape=(1,), dtype=DataType.FP32, data=b"\x00\x00\x00\x00"
            )
        },
        task_descriptor=TaskDescriptor(
            task_id="g2",
            form="generative_evolve",
            safety_tier="research",
            deadline_ms=500,
            submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=400.0,
        required_modalities=(Modality.DENSE_VECTOR,),
    )
    em = mod.handle(inp)
    assert em is not None
    body = json.loads(em.payload.decode())
    assert body.get("exploration_only") is True or body.get("draft_seq") >= 1
