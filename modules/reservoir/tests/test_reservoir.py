"""Phase B: reservoir dynamics + readout."""
from __future__ import annotations

import json
import struct
from datetime import datetime, timezone

from organism_sdk.contract import DataType, Modality, Severity
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.module import run_handle
from organism_sdk.workspace import WorkspaceClient
from reservoir.module import ReservoirModule


def test_reservoir_fit_and_step():
    mod = ReservoirModule(size=16, seed=1)
    assert not [i for i in mod.declare_contract().validate() if i.severity == Severity.ERROR]
    inputs = [[0.1 * (i % 5)] * 8 for i in range(20)]
    targets = [0.5 + 0.02 * i for i in range(20)]
    mod.fit_readout(inputs, targets)
    assert mod.readout.fitted
    st = mod.step([0.3] * 8)
    assert len(st) == 16
    data = struct.pack("<" + "f" * 8, *([0.3] * 8))
    ws = WorkspaceClient()
    inp = PerceptionInput(
        modalities={
            Modality.DENSE_VECTOR: ModalityPayload(
                modality=Modality.DENSE_VECTOR, shape=(8,), dtype=DataType.FP32, data=data
            )
        },
        task_descriptor=TaskDescriptor(
            task_id="r1", form="prediction", safety_tier="medium",
            deadline_ms=500, submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=400.0,
        required_modalities=(Modality.DENSE_VECTOR,),
    )
    em = run_handle(mod, inp)
    body = json.loads(em.payload.decode())
    assert "point" in body
