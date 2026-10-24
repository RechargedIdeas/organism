"""M1 exit: contract compiles; engine registers; health probe responds; contract:validate green."""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

from deterministic_engine.engine import DeterministicEngine
from organism_sdk.contract import Severity
from organism_sdk.health import HealthServer
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.contract import DataType, Modality
from organism_sdk.module import run_handle
from organism_sdk.registry import RegistryClient
from organism_sdk.workspace import WorkspaceClient


def test_contract_validate_green():
    eng = DeterministicEngine()
    issues = eng.declare_contract().validate()
    assert [i for i in issues if i.severity == Severity.ERROR] == []


def test_engine_registers():
    eng = DeterministicEngine()
    reg = RegistryClient()
    c = eng.declare_contract()
    resp = reg.register(
        c,
        artifact_digest=c.identity.artifact_digest,
        author_signature=b"sig",
        module=eng,
        test_bypass_promote="DELIBERATION",
    )
    assert resp.module_id == "deterministic_engine"
    handles = reg.query(__import__("organism_sdk.registry", fromlist=["CapabilityFilter"]).CapabilityFilter())
    assert any(h.module_id == "deterministic_engine" for h in handles)
    report = reg.health("deterministic_engine")
    assert report.status == "HEALTHY"


def test_health_probe_responds():
    eng = DeterministicEngine()
    srv = HealthServer(eng, host="127.0.0.1", port=0, path="/health")
    srv.serve_forever(background=True)
    try:
        with urllib.request.urlopen(srv.url, timeout=2) as resp:
            body = json.loads(resp.read().decode())
        assert body["status"] == "HEALTHY"
        assert body["module_id"] == "deterministic_engine"
    finally:
        srv.shutdown()


def test_handle_justify_control_actuation():
    eng = DeterministicEngine()
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    inp = PerceptionInput(
        modalities={
            Modality.TABULAR: ModalityPayload(
                modality=Modality.TABULAR, shape=(1, 8), dtype=DataType.FP32, data=b"\x00" * 32
            )
        },
        task_descriptor=TaskDescriptor(
            task_id="task-1",
            form="control_actuation",
            safety_tier="high",
            deadline_ms=1000,
            submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=900.0,
        required_modalities=(Modality.TABULAR,),
    )
    emission = run_handle(eng, inp)
    assert emission.justification is not None
    assert emission.justification.kind.value == "RULE_TRACE"
    assert emission.metadata["rule_fired"] == "actuate_control"


def test_critical_holds():
    eng = DeterministicEngine()
    ws = WorkspaceClient()
    inp = PerceptionInput(
        modalities={
            Modality.TABULAR: ModalityPayload(
                modality=Modality.TABULAR, shape=(1, 8), dtype=DataType.FP32, data=b"\x00" * 32
            )
        },
        task_descriptor=TaskDescriptor(
            task_id="task-2",
            form="control_actuation",
            safety_tier="critical",
            deadline_ms=1000,
            submitted_at=datetime.now(timezone.utc),
        ),
        workspace_reader=ws.reader(),
        deadline_remaining_ms=900.0,
        required_modalities=(Modality.TABULAR,),
    )
    emission = run_handle(eng, inp)
    assert emission.metadata["rule_fired"] == "hold_on_critical_without_cert"
