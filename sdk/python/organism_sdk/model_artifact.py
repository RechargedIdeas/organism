"""ModelArtifact manifest (A8): what a model release must state before it is served.

A release names its weights and tokenizer by digest, says how it was quantised, lists the adapters
applied on top of the base weights, states its licence and data provenance, and points at the gate
report that cleared it. Digests are ``sha256:`` followed by 64 lower-case hex digits.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from organism_sdk.contract import Severity, ValidationIssue

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def is_digest(text: str) -> bool:
    return _DIGEST.fullmatch(text) is not None


@dataclass(frozen=True)
class ModelArtifact:
    model_id: str
    version: str
    weights_digest: str
    tokenizer_digest: str
    quantisation: str
    license: str
    gate_report_digest: str
    # Adapter digests in the order they were applied, base first.
    adapter_lineage: tuple[str, ...] = ()
    # Data sources, as identifiers or digests. At least one is required.
    data_provenance: tuple[str, ...] = ()

    def validate(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        def missing(path: str) -> None:
            issues.append(ValidationIssue(Severity.ERROR, "artifact_field_missing", path, f"{path} required"))

        def digest(path: str, value: str) -> None:
            if not value:
                missing(path)
            elif not is_digest(value):
                issues.append(ValidationIssue(Severity.ERROR, "digest_invalid", path,
                                              "digest must be sha256: and 64 lower-case hex digits"))

        if not self.model_id:
            missing("artifact.model_id")
        if not self.version:
            missing("artifact.version")
        digest("artifact.weights_digest", self.weights_digest)
        digest("artifact.tokenizer_digest", self.tokenizer_digest)
        if not self.quantisation:
            missing("artifact.quantisation")
        seen: set[str] = set()
        for i, entry in enumerate(self.adapter_lineage):
            path = f"artifact.adapter_lineage[{i}]"
            if not is_digest(entry):
                issues.append(ValidationIssue(Severity.ERROR, "digest_invalid", path,
                                              "digest must be sha256: and 64 lower-case hex digits"))
            elif entry in seen:
                issues.append(ValidationIssue(Severity.ERROR, "adapter_lineage_duplicate", path,
                                              "adapter appears twice in the lineage"))
            seen.add(entry)
        if not self.license:
            missing("artifact.license")
        if not self.data_provenance:
            missing("artifact.data_provenance")
        for i, entry in enumerate(self.data_provenance):
            if not entry:
                missing(f"artifact.data_provenance[{i}]")
        digest("artifact.gate_report_digest", self.gate_report_digest)
        return issues

    def is_releasable(self) -> bool:
        return not any(i.severity == Severity.ERROR for i in self.validate())
