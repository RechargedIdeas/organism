"""M2 exit: register/query/promote round-trip; workspace bind/unbind exactness."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from deterministic_engine.engine import DeterministicEngine
from organism_sdk.hypervector import Hypervector
from organism_sdk.registry import CapabilityFilter, RegistryClient, ShadowValidationRecord
from organism_sdk.contract import ModuleRole
from organism_sdk.workspace import BindingRecord, WorkspaceClient


def test_register_query_promote_roundtrip():
    eng = DeterministicEngine()
    reg = RegistryClient()
    c = eng.declare_contract()
    resp = reg.register(
        c,
        artifact_digest=c.identity.artifact_digest,
        author_signature=b"sig",
        module=eng,
        initial_state="PROPOSED",
    )
    assert resp.initial_state == "PROPOSED"

    # Adjacent promotions
    for frm, to in [
        ("PROPOSED", "SANDBOXED"),
        ("SANDBOXED", "SHADOW_VALIDATED"),
        ("SHADOW_VALIDATED", "EXPLORATION"),
        ("EXPLORATION", "DELIBERATION"),
    ]:
        pr = reg.promote(
            resp.module_id,
            frm,
            to,
            shadow_records=[
                ShadowValidationRecord(
                    invocations=100, incumbent_error=0.1, candidate_error=0.09, p95_latency_ms=2.0
                )
            ],
            approver_signature=b"approve",
        )
        assert pr.accepted, pr.validation_issues

    handles = reg.query(
        CapabilityFilter(roles=(ModuleRole.GOVERNANCE,), min_lifecycle_state="DELIBERATION")
    )
    assert len(handles) == 1
    assert handles[0].state == "DELIBERATION"
    assert handles[0].module_id == "deterministic_engine"


def test_workspace_bind_unbind_exactness():
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    role = Hypervector.random()
    filler = Hypervector.random()
    bound = ws.bind_exact(role, filler, tags=("governance",), module_id="deterministic_engine")
    # Exactness: hypervector == role XOR filler
    assert bound.hypervector.to_bytes_be() == role.bind(filler).to_bytes_be()
    # Unbind recovers filler
    recovered = bound.hypervector.unbind(role)
    assert recovered.to_bytes_be() == filler.to_bytes_be()
    # Remove and confirm gone
    prior = ws.unbind(bound.binding_id)
    assert prior is not None
    assert ws.read_by_binding_id(bound.binding_id) is None


def test_workspace_write_rejects_out_of_scope_tags():
    ws = WorkspaceClient(write_tags=("allowed",), read_tags=("*",))
    role = Hypervector.random()
    filler = Hypervector.random()
    hv = role.bind(filler)
    rec = BindingRecord(
        binding_id=uuid4(),
        hypervector=hv,
        role=role,
        filler=filler,
        tags=("forbidden",),
        module_id="x",
    )
    result = ws.write(rec)
    assert result.status == "REJECTED"
    assert result.reason_code == "capability_scope_missing"
