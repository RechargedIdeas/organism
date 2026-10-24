"""Phase B: three-level causal verifier."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from organism_sdk.contract import DataType, Modality, Severity
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.module import run_handle
from organism_sdk.workspace import WorkspaceClient
from neurosymbolic.module import NeurosymbolicVerifier


def test_three_level_pass_and_cert():
    mod = NeurosymbolicVerifier(min_recognition=0.5)
    assert not [i for i in mod.declare_contract().validate() if i.severity == Severity.ERROR]
    r = mod.three_level_check(
        state={"thermal": 0.2, "viability": 0.9, "actuation": 0.0, "calibration": 1.0},
        action_node="actuation",
        action_value=0.5,
    )
    assert r.passed
    assert r.recognition >= 0.5
    ws = WorkspaceClient()
    tab = json.dumps({"thermal": 0.2, "viability": 0.9, "action_node": "actuation", "action_value": 0.5}).encode()
    inp = PerceptionInput(
        modalities={
            Modality.TABULAR: ModalityPayload(
                modality=Modality.TABULAR, shape=(1,), dtype=DataType.FP32, data=tab
            )
        },
        task_descriptor=TaskDescriptor(
            task_id="n1", form="verify", safety_tier="high",
            deadline_ms=500, submitted_at=datetime.now(timezone.utc),
            metadata={"action_node": "actuation", "action_value": "0.5"},
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=400.0,
        required_modalities=(Modality.TABULAR,),
    )
    em = run_handle(mod, inp)
    assert em.justification is not None
    assert em.justification.kind.value == "CAUSAL_CERT"
    body = json.loads(em.payload.decode())
    assert "recognition" in body


def test_thermal_crisis_lowers_interventional():
    mod = NeurosymbolicVerifier(min_recognition=0.9)
    r = mod.three_level_check(
        state={"thermal": 0.95, "viability": 0.5, "actuation": 0.0},
        action_node="actuation",
        action_value=1.0,
    )
    assert r.interventional_score < 0.3
