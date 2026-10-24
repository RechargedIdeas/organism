"""Phase B: energy / Hopfield solver."""
from __future__ import annotations

import json
import struct
from datetime import datetime, timezone

from organism_sdk.contract import DataType, Modality, Severity
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.module import run_handle
from organism_sdk.workspace import WorkspaceClient
from energy_hopfield.module import EnergyHopfieldModule


def test_energy_minimize_and_cert():
    mod = EnergyHopfieldModule()
    assert not [i for i in mod.declare_contract().validate() if i.severity == Severity.ERROR]
    mod.store_pattern([1, 1, -1, -1, 1, -1, 1, -1])
    x, e, ok = mod.minimize([0.5] * 8)
    assert len(x) == 8
    data = struct.pack("<" + "f" * 8, *([0.6] * 8))
    ws = WorkspaceClient()
    inp = PerceptionInput(
        modalities={
            Modality.DENSE_VECTOR: ModalityPayload(
                modality=Modality.DENSE_VECTOR, shape=(8,), dtype=DataType.FP32, data=data
            )
        },
        task_descriptor=TaskDescriptor(
            task_id="e1", form="assignment", safety_tier="medium",
            deadline_ms=500, submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=400.0,
        required_modalities=(Modality.DENSE_VECTOR,),
    )
    em = run_handle(mod, inp)
    assert em.justification is not None
    body = json.loads(em.payload.decode())
    assert "energy" in body
