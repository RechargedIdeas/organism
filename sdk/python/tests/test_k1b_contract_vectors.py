"""K1b contract additions against the vectors: output forms (A1), tool contract (A2), human confirmation (A3),
model artifact manifest (A8)."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from organism_sdk.contract import (
    JustificationKind,
    JustificationSpec,
    MaxSafetyTier,
    OutputForm,
    Severity,
    SubstrateContract,
    ToolConfinement,
    ToolConfirmation,
    ToolContract,
    ToolNetwork,
    ValidationIssue,
)
from organism_sdk.model_artifact import ModelArtifact, is_digest

from .test_contract_validate import _base_contract

VECTORS = Path(__file__).resolve().parents[3] / "conformance" / "vectors"


def _cases(name: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads((VECTORS / f"{name}.json").read_text(encoding="utf-8"))["cases"]
    return cases


def _found(issues: list[ValidationIssue]) -> list[dict[str, Any]]:
    return [{"severity": i.severity.value, "code": i.code, "field_path": i.field_path} for i in issues]


@pytest.mark.parametrize("case", _cases("tool"), ids=lambda c: c["name"])
def test_tool_vectors(case: dict[str, Any]) -> None:
    t = case["tool"]
    tool = ToolContract(
        name=t["name"], schema_json=t["schema"], risk_tier=MaxSafetyTier(t["risk_tier"]),
        confirmation=ToolConfirmation(t["confirmation"]), network=ToolNetwork(t["network"]),
        confinement=ToolConfinement(t["confinement"]),
    )
    assert _found(tool.validate()) == case["issues"]
    assert tool.is_registrable() is case["registered"]


@pytest.mark.parametrize("case", _cases("model_artifact"), ids=lambda c: c["name"])
def test_model_artifact_vectors(case: dict[str, Any]) -> None:
    a = dict(case["artifact"])
    a["adapter_lineage"] = tuple(a["adapter_lineage"])
    a["data_provenance"] = tuple(a["data_provenance"])
    artifact = ModelArtifact(**a)
    assert _found(artifact.validate()) == case["issues"]
    assert artifact.is_releasable() is case["releasable"]


def test_digest_format() -> None:
    assert is_digest("sha256:" + "ab" * 32)
    assert not is_digest("sha256:" + "AB" * 32)
    assert not is_digest("sha256:" + "ab" * 32 + "\n")


def _with_output(form: OutputForm, **kw: Any) -> SubstrateContract:
    c = _base_contract()
    return dataclasses.replace(c, emission=dataclasses.replace(c.emission, output_form=form, **kw))


@pytest.mark.parametrize("form", [OutputForm.TEXT, OutputForm.TOKEN_STREAM])
def test_language_output_forms_validate(form: OutputForm) -> None:
    assert _with_output(form).validate() == []


def test_tool_call_without_justification_warns() -> None:
    issues = _with_output(OutputForm.TOOL_CALL, requires_justification_for=()).validate()
    assert (Severity.WARNING, "tool_call_without_justification") in [(i.severity, i.code) for i in issues]
    ok = _with_output(OutputForm.TOOL_CALL, requires_justification_for=("irreversible",))
    assert "tool_call_without_justification" not in [i.code for i in ok.validate()]


def test_human_confirmation_kind_and_proto() -> None:
    c = dataclasses.replace(_with_output(OutputForm.TOOL_CALL, requires_justification_for=("irreversible",)),
                            justification=JustificationSpec(kind=JustificationKind.HUMAN_CONFIRMATION))
    assert c.validate() == []
    proto = c.to_proto()
    from organism_sdk._proto_path import ensure_proto_path

    ensure_proto_path()
    from organism.v1 import contract_pb2

    assert proto.justification.kind == contract_pb2.JUSTIFICATION_HUMAN_CONFIRMATION
    assert proto.emission.output_form == contract_pb2.OUTPUT_TOOL_CALL
