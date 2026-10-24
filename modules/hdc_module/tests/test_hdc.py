"""Phase B: hdc_module fingerprint / retrieve."""
from __future__ import annotations

import json
import struct
from datetime import datetime, timezone

from organism_sdk.contract import DataType, Modality, Severity
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.module import run_handle
from organism_sdk.workspace import WorkspaceClient
from hdc_module.module import HDCModule


def test_hdc_fingerprint_store_retrieve():
    mod = HDCModule(seed=42)
    c = mod.declare_contract()
    assert not [i for i in c.validate() if i.severity == Severity.ERROR]
    fp = mod.fingerprint(["alpha", "beta", "gamma"])
    mod.store("alpha", fp)
    hits = mod.retrieve(fp, k=1)
    assert hits and hits[0][0] == "alpha"
    assert hits[0][1] > 0.9
    data = struct.pack("<" + "f" * 8, *([0.2] * 8))
    ws = WorkspaceClient()
    inp = PerceptionInput(
        modalities={
            Modality.DENSE_VECTOR: ModalityPayload(
                modality=Modality.DENSE_VECTOR, shape=(8,), dtype=DataType.FP32, data=data
            )
        },
        task_descriptor=TaskDescriptor(
            task_id="h1", form="memory", safety_tier="low",
            deadline_ms=500, submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=400.0,
        required_modalities=(Modality.DENSE_VECTOR,),
    )
    em = run_handle(mod, inp)
    body = json.loads(em.payload.decode())
    assert body["memory_size"] >= 1
