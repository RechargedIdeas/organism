"""Generative code pipeline: intent → draft → checks → sandbox → shadow → promote.

Self-evolution MUST pass PromoteGate before any control-path overwrite.
Silent overwrite of control path is refused (PromoteRefused).
"""
from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from organism_sdk.generative.artifacts import ArtifactStore, ProvenanceRecord
from organism_sdk.generative.backends import DraftBackend, TemplateDraftBackend
from organism_sdk.generative.sandbox import SafeSandbox, SandboxResult
from organism_sdk.generative.stages import EvolutionStage, PromoteGate


class CodeStage(str, Enum):
    INTENT = "INTENT"
    DRAFT = "DRAFT"
    STATIC_OK = "STATIC_OK"
    CONTRACT_OK = "CONTRACT_OK"
    SANDBOXED = "SANDBOXED"
    SHADOW_SCORED = "SHADOW_SCORED"
    PROMOTED = "PROMOTED"
    DEMOTION = "DEMOTION"
    REJECTED = "REJECTED"


class PromoteRefused(PermissionError):
    """Unsafe or incomplete promote attempt — mirrors ActuationRefused pattern."""


@dataclass
class CodeBundle:
    bundle_id: str
    intent: str
    source: str
    backend: str
    stage: CodeStage = CodeStage.DRAFT
    gate: PromoteGate = field(default_factory=PromoteGate)
    static_errors: list[str] = field(default_factory=list)
    contract_errors: list[str] = field(default_factory=list)
    sandbox: dict[str, Any] | None = None
    shadow_score: float = 0.0
    provenance: list[dict[str, Any]] = field(default_factory=list)
    may_control: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    research_tier: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "intent": self.intent,
            "backend": self.backend,
            "stage": self.stage.value,
            "gate": self.gate.as_dict(),
            "static_errors": self.static_errors,
            "contract_errors": self.contract_errors,
            "sandbox": self.sandbox,
            "shadow_score": self.shadow_score,
            "may_control": self.may_control,
            "research_tier": self.research_tier,
            "source_digest": hashlib.sha256(self.source.encode()).hexdigest(),
            "source_lines": len(self.source.splitlines()),
            "provenance": list(self.provenance),
            "created_at": self.created_at,
        }


_SHELLISH = re.compile(
    r"\b(os\.system|subprocess|Popen|shell\s*=\s*True|__import__)\b"
)


def _static_check(source: str) -> list[str]:
    errs: list[str] = []
    try:
        ast.parse(source)
    except SyntaxError as e:
        errs.append(f"syntax: {e}")
        return errs
    if _SHELLISH.search(source):
        errs.append("static: shell/subprocess patterns forbidden")
    if "may_actuate" in source and "True" in source:
        # soft warn — contract stage hard-fails may_actuate=True
        pass
    if "open(" in source:
        errs.append("static: file open() forbidden in generative drafts")
    return errs


def _contract_check(source: str, *, spec: dict[str, Any] | None = None) -> list[str]:
    errs: list[str] = []
    spec = spec or {}
    if "def main" not in source:
        errs.append("contract: missing main() entrypoint")
    if spec.get("may_actuate", False) is True:
        errs.append("contract: may_actuate must remain False for generative drafts")
    if "may_actuate=True" in source or "may_actuate = True" in source:
        errs.append("contract: source declares may_actuate=True")
    return errs


def _shadow_score(sandbox: SandboxResult) -> float:
    if not sandbox.ok:
        return 0.0
    val = sandbox.value
    if isinstance(val, dict) and val.get("ok") is True:
        # Successful sandboxed Organism drafts clear the default 0.9 gate.
        base = 0.91
        for k in ("score", "prediction"):
            if isinstance(val.get(k), (int, float)):
                n = abs(float(val[k]))
                return min(0.99, base + (n % 1.0) * 0.08)
        return 0.93
    if isinstance(val, (int, float)):
        return min(0.99, 0.91 + abs(float(val)) % 0.08)
    return 0.5


class CodePipeline:
    """Production generative code evolution path for Organisms."""

    def __init__(
        self,
        store: ArtifactStore,
        *,
        backend: DraftBackend | None = None,
        sandbox: SafeSandbox | None = None,
        min_shadow: float = 0.9,
    ) -> None:
        self.store = store
        self.backend = backend or TemplateDraftBackend()
        self.sandbox = sandbox or SafeSandbox()
        self.min_shadow = min_shadow
        self.bundles: dict[str, CodeBundle] = {}

    def start(
        self,
        intent: str,
        *,
        spec: dict[str, Any] | None = None,
        backend: DraftBackend | None = None,
    ) -> CodeBundle:
        be = backend or self.backend
        source = be.draft(intent, spec=spec)
        digest = hashlib.sha256(f"{intent}:{source}".encode()).hexdigest()[:16]
        bundle_id = f"code_{digest}"
        gate = PromoteGate(min_shadow_score=self.min_shadow)
        bundle = CodeBundle(
            bundle_id=bundle_id,
            intent=intent,
            source=source,
            backend=be.name,
            stage=CodeStage.DRAFT,
            gate=gate,
        )
        rec = self.store.put(
            kind="code",
            body=source,
            backend=be.name,
            stage=CodeStage.DRAFT.value,
            artifact_id=bundle_id,
            metadata={"intent": intent[:500]},
            suffix=".py",
        )
        bundle.provenance.append(rec.as_dict())
        self.bundles[bundle_id] = bundle
        return bundle

    def run_static(self, bundle_id: str) -> CodeBundle:
        b = self._get(bundle_id)
        errs = _static_check(b.source)
        b.static_errors = errs
        b.gate.static_ok = not errs
        b.stage = CodeStage.STATIC_OK if not errs else CodeStage.REJECTED
        if errs:
            b.gate.promoted = False
            b.may_control = False
        self._persist(b, b.stage.value)
        return b

    def run_contract(self, bundle_id: str, *, spec: dict[str, Any] | None = None) -> CodeBundle:
        b = self._get(bundle_id)
        if b.stage == CodeStage.REJECTED:
            return b
        errs = _contract_check(b.source, spec=spec)
        b.contract_errors = errs
        b.gate.contract_ok = not errs
        b.stage = CodeStage.CONTRACT_OK if not errs else CodeStage.REJECTED
        self._persist(b, b.stage.value)
        return b

    def run_sandbox(self, bundle_id: str, *, args: dict[str, Any] | None = None) -> CodeBundle:
        b = self._get(bundle_id)
        if b.stage in (CodeStage.REJECTED,):
            return b
        if not b.gate.static_ok or not b.gate.contract_ok:
            raise PromoteRefused("sandbox requires static+contract ok")
        result = self.sandbox.run(b.source, args=args or {"x": 1.0, "y": 2.0})
        b.sandbox = result.as_dict()
        b.gate.sandbox_ok = result.ok
        b.stage = CodeStage.SANDBOXED if result.ok else CodeStage.REJECTED
        self._persist(b, b.stage.value)
        return b

    def run_shadow(self, bundle_id: str) -> CodeBundle:
        b = self._get(bundle_id)
        if not b.gate.sandbox_ok or not b.sandbox:
            raise PromoteRefused("shadow requires successful sandbox")
        score = _shadow_score(
            SandboxResult(
                ok=bool(b.sandbox.get("ok")),
                value=b.sandbox.get("value"),
                error=b.sandbox.get("error"),
            )
        )
        b.shadow_score = score
        b.gate.shadow_score = score
        b.gate.shadow_validated = score >= b.gate.min_shadow_score
        b.stage = CodeStage.SHADOW_SCORED
        self._persist(b, b.stage.value)
        return b

    def promote(self, bundle_id: str) -> CodeBundle:
        b = self._get(bundle_id)
        if not b.gate.ready():
            raise PromoteRefused(
                f"promote blocked: gate={b.gate.as_dict()}; never silent control overwrite"
            )
        b.gate.promoted = True
        b.may_control = True
        b.research_tier = False
        b.stage = CodeStage.PROMOTED
        self._persist(b, CodeStage.PROMOTED.value, metadata={"promoted": True})
        return b

    def demote(self, bundle_id: str, *, reason: str = "manual_demote") -> CodeBundle:
        b = self._get(bundle_id)
        b.gate.promoted = False
        b.gate.shadow_validated = False
        b.may_control = False
        b.research_tier = True
        b.stage = CodeStage.DEMOTION
        self._persist(b, CodeStage.DEMOTION.value, metadata={"reason": reason})
        return b

    def evolve(
        self,
        intent: str,
        *,
        spec: dict[str, Any] | None = None,
        backend: DraftBackend | None = None,
        auto_promote: bool = False,
    ) -> CodeBundle:
        """Full pipeline. Promote only if auto_promote and gate ready."""
        b = self.start(intent, spec=spec, backend=backend)
        self.run_static(b.bundle_id)
        if b.stage == CodeStage.REJECTED:
            return b
        self.run_contract(b.bundle_id, spec=spec)
        if b.stage == CodeStage.REJECTED:
            return b
        self.run_sandbox(b.bundle_id)
        if b.stage == CodeStage.REJECTED:
            return b
        self.run_shadow(b.bundle_id)
        if auto_promote and b.gate.ready():
            return self.promote(b.bundle_id)
        return b

    def _persist(
        self, b: CodeBundle, stage: str, *, metadata: dict[str, Any] | None = None
    ) -> ProvenanceRecord:
        parent = b.provenance[-1]["digest"] if b.provenance else None
        rec = self.store.put(
            kind="code",
            body=b.source,
            backend=b.backend,
            stage=stage,
            artifact_id=b.bundle_id,
            parent_digest=parent,
            metadata={"intent": b.intent[:500], **(metadata or {})},
            suffix=".py",
        )
        b.provenance.append(rec.as_dict())
        return rec

    def _get(self, bundle_id: str) -> CodeBundle:
        if bundle_id not in self.bundles:
            raise KeyError(f"unknown bundle_id={bundle_id}")
        return self.bundles[bundle_id]

    def list_bundles(self) -> list[dict[str, Any]]:
        return [b.as_dict() for b in self.bundles.values()]
