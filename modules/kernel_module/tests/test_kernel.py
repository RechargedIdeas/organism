"""Phase B: kernel_module contract, ridge fit, handle."""
from __future__ import annotations

import json
import struct
from datetime import datetime, timezone

from organism_sdk.contract import DataType, Modality, Severity
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.module import run_handle
from organism_sdk.registry import RegistryClient
from organism_sdk.workspace import WorkspaceClient
from kernel_module.module import KernelModule, MODULE_ID


def _inp(form: str = "pattern_recognition") -> PerceptionInput:
    data = struct.pack("<" + "f" * 8, *([0.5] * 8))
    ws = WorkspaceClient()
    return PerceptionInput(
        modalities={
            Modality.DENSE_VECTOR: ModalityPayload(
                modality=Modality.DENSE_VECTOR, shape=(8,), dtype=DataType.FP32, data=data
            )
        },
        task_descriptor=TaskDescriptor(
            task_id="k1",
            form=form,
            safety_tier="medium",
            deadline_ms=1000,
            submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=800.0,
        required_modalities=(Modality.DENSE_VECTOR,),
    )


def test_kernel_contract_and_register():
    mod = KernelModule()
    c = mod.declare_contract()
    assert not [i for i in c.validate() if i.severity == Severity.ERROR]
    reg = RegistryClient()
    resp = reg.register(
        c,
        artifact_digest=c.identity.artifact_digest,
        author_signature=b"s",
        module=mod,
        test_bypass_promote="DELIBERATION",
    )
    assert resp.module_id == MODULE_ID


def test_kernel_ridge_and_handle():
    mod = KernelModule()
    X = [[0.1 * i] * 8 for i in range(12)]
    y = [0.05 * i for i in range(12)]
    mod.fit_readout(X, y)
    assert mod.readout.fitted
    em = run_handle(mod, _inp())
    body = json.loads(em.payload.decode())
    assert "point" in body
    assert 0.0 <= body["point"] <= 1.0
