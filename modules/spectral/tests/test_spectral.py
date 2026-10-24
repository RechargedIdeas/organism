"""Phase B: spectral Haar front-end."""
from __future__ import annotations

import json
import struct
from datetime import datetime, timezone

from organism_sdk.contract import DataType, Modality, Severity
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.module import run_handle
from organism_sdk.workspace import WorkspaceClient
from spectral.module import SpectralModule, haar_dwt


def test_haar_and_handle():
    coeffs = haar_dwt([1.0, 2.0, 3.0, 4.0])
    assert len(coeffs) == 4
    mod = SpectralModule()
    assert not [i for i in mod.declare_contract().validate() if i.severity == Severity.ERROR]
    data = struct.pack("<" + "f" * 16, *([0.25] * 16))
    ws = WorkspaceClient()
    inp = PerceptionInput(
        modalities={
            Modality.DENSE_VECTOR: ModalityPayload(
                modality=Modality.DENSE_VECTOR, shape=(16,), dtype=DataType.FP32, data=data
            )
        },
        task_descriptor=TaskDescriptor(
            task_id="s1", form="feature", safety_tier="low",
            deadline_ms=500, submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=400.0,
        required_modalities=(Modality.DENSE_VECTOR,),
    )
    em = run_handle(mod, inp)
    body = json.loads(em.payload.decode())
    assert body["basis"] == "haar"
    assert "features" in body
