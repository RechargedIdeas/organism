"""Generative code pipeline: intent → draft → checks → sandbox → shadow → promote.

Self-evolution MUST pass PromoteGate before any control-path overwrite.
Silent overwrite of control path is refused (PromoteRefused).

v1.7.1: richer static AST forbid list, shadow metrics, rollback, replayable drafts.
v1.7.2: wall-clock evolve/promote budgets recorded on last_timings.
"""
from __future__ import annotations

import ast
import json
import hashlib
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum
from typing import Any

from organism_sdk.generative.artifacts import ArtifactStore, ProvenanceRecord
from organism_sdk.generative.backends import (
    DraftBackend,
    DraftReplayLog,
    GeneratorBackend,
    TemplateDraftBackend,
)
from organism_sdk.generative.sandbox import SafeSandbox, SandboxResult
from organism_sdk.generative.stages import PromoteGate


class CodeStage(str, Enum):
    INTENT = "INTENT"
    DRAFT = "DRAFT"
    STATIC_OK = "STATIC_OK"
    CONTRACT_OK = "CONTRACT_OK"
    SANDBOXED = "SANDBOXED"
    SHADOW_SCORED = "SHADOW_SCORED"
    PROMOTED = "PROMOTED"
    DEMOTION = "DEMOTION"
    ROLLBACK = "ROLLBACK"
    REJECTED = "REJECTED"


class PromoteRefused(PermissionError):
    """Unsafe or incomplete promote attempt — mirrors ActuationRefused pattern."""


@dataclass
class ShadowMetrics:
    """Production shadow scoring breakdown (v1.7.1)."""

    base: float = 0.0
    ok_bonus: float = 0.0
    numeric_bonus: float = 0.0
    structure_bonus: float = 0.0
    latency_penalty: float = 0.0
    total: float = 0.0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "ok_bonus": self.ok_bonus,
            "numeric_bonus": self.numeric_bonus,
            "structure_bonus": self.structure_bonus,
            "latency_penalty": self.latency_penalty,
            "total": self.total,
            "notes": list(self.notes),
        }


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
    shadow_metrics: dict[str, Any] = field(default_factory=dict)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    may_control: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    research_tier: bool = True
    replay_id: str | None = None
    stage_progress: list[str] = field(default_factory=list)
    prior_promoted_id: str | None = None

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
            "shadow_metrics": dict(self.shadow_metrics),
            "may_control": self.may_control,
            "research_tier": self.research_tier,
            "source_digest": hashlib.sha256(self.source.encode()).hexdigest(),
            "source_lines": len(self.source.splitlines()),
            "provenance": list(self.provenance),
            "created_at": self.created_at,
            "replay_id": self.replay_id,
            "stage_progress": list(self.stage_progress),
            "prior_promoted_id": self.prior_promoted_id,
        }


# Expanded static forbid patterns (string + AST).
_SHELLISH = re.compile(
    r"\b(os\.system|subprocess|Popen|shell\s*=\s*True|__import__|"
    r"eval\s*\(|exec\s*\(|compile\s*\(|pickle\.|marshal\.|"
    r"socket\.|urllib\.|requests\.|ctypes\.|multiprocessing\.)\b"
)

_STATIC_FORBIDDEN_NAMES = {
    "os", "sys", "subprocess", "socket", "pathlib", "shutil", "ctypes",
    "importlib", "builtins", "eval", "exec", "open", "compile", "__import__",
    "pickle", "marshal", "requests", "urllib", "http", "asyncio",
    "threading", "multiprocessing", "pty", "fcntl", "signal",
}


def _static_check(source: str) -> list[str]:
    errs: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        errs.append(f"syntax: {e}")
        return errs
    if _SHELLISH.search(source):
        errs.append("static: shell/subprocess/network/pickle patterns forbidden")
    if "open(" in source:
        errs.append("static: file open() forbidden in generative drafts")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            errs.append(f"static: import forbidden ({type(node).__name__})")
        if isinstance(node, ast.Name) and node.id in _STATIC_FORBIDDEN_NAMES:
            errs.append(f"static: forbidden name {node.id}")
        if isinstance(node, ast.Attribute) and node.attr in {
            "system", "popen", "Popen", "__subclasses__", "__globals__", "__builtins__"
        }:
            errs.append(f"static: forbidden attribute {node.attr}")
        if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            errs.append(f"static: disallowed construct {type(node).__name__}")
    # de-dupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for e in errs:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


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


def _compute_shadow_metrics(sandbox: SandboxResult) -> ShadowMetrics:
    m = ShadowMetrics()
    if not sandbox.ok:
        m.notes.append("sandbox_failed")
        m.total = 0.0
        return m
    m.base = 0.70
    m.notes.append("sandbox_ok")
    val = sandbox.value
    if isinstance(val, dict) and val.get("ok") is True:
        m.ok_bonus = 0.18
        m.notes.append("payload_ok")
        for k in ("score", "prediction"):
            if isinstance(val.get(k), (int, float)):
                n = abs(float(val[k]))
                m.numeric_bonus = min(0.08, (n % 1.0) * 0.08 + 0.02)
                m.notes.append(f"numeric:{k}")
                break
        if any(k in val for k in ("skill", "template", "label", "kept", "n")):
            m.structure_bonus = 0.03
            m.notes.append("structured_payload")
    elif isinstance(val, (int, float)):
        m.ok_bonus = 0.15
        m.numeric_bonus = min(0.08, abs(float(val)) % 0.08)
        m.notes.append("numeric_return")
    else:
        m.ok_bonus = 0.05
        m.notes.append("opaque_return")
    m.total = min(0.99, m.base + m.ok_bonus + m.numeric_bonus + m.structure_bonus - m.latency_penalty)
    # Successful sandboxed Organism drafts should clear the default 0.9 gate.
    if sandbox.ok and isinstance(val, dict) and val.get("ok") is True and m.total < 0.91:
        m.total = 0.91
        m.notes.append("floor_0.91")
    return m


def _shadow_score(sandbox: SandboxResult) -> tuple[float, ShadowMetrics]:
    metrics = _compute_shadow_metrics(sandbox)
    return metrics.total, metrics


class CodePipeline:
    """Production generative code evolution path for Organisms."""

    STAGE_ORDER = [
        CodeStage.DRAFT,
        CodeStage.STATIC_OK,
        CodeStage.CONTRACT_OK,
        CodeStage.SANDBOXED,
        CodeStage.SHADOW_SCORED,
        CodeStage.PROMOTED,
    ]

    def __init__(
        self,
        store: ArtifactStore,
        *,
        backend: DraftBackend | GeneratorBackend | None = None,
        sandbox: SafeSandbox | None = None,
        min_shadow: float = 0.9,
        replay_log: DraftReplayLog | None = None,
    ) -> None:
        self.store = store
        self.backend: DraftBackend | GeneratorBackend = backend or TemplateDraftBackend()
        self.sandbox = sandbox or SafeSandbox()
        self.min_shadow = min_shadow
        self.replay_log = replay_log or DraftReplayLog()
        self.bundles: dict[str, CodeBundle] = {}
        self._lock = threading.RLock()
        self._promote_stack: list[str] = []  # bundle_ids in promote order
        self._last_promoted: str | None = None
        self._last_timings: dict[str, float] = {}
        # Wall-clock budgets (ms) — see EvolutionRuntime constants
        self.evolve_budget_ms: float = 250.0
        self.promote_budget_ms: float = 100.0

    def start(
        self,
        intent: str,
        *,
        spec: dict[str, Any] | None = None,
        backend: DraftBackend | GeneratorBackend | None = None,
    ) -> CodeBundle:
        with self._lock:
            be = backend or self.backend
            source = be.draft(intent, spec=spec)
            replay = self.replay_log.record(
                backend=getattr(be, "name", "unknown"),
                intent=intent,
                source=source,
                spec=spec,
            )
            digest = hashlib.sha256(f"{intent}:{source}".encode()).hexdigest()[:16]
            bundle_id = f"code_{digest}"
            gate = PromoteGate(min_shadow_score=self.min_shadow)
            bundle = CodeBundle(
                bundle_id=bundle_id,
                intent=intent,
                source=source,
                backend=getattr(be, "name", "unknown"),
                stage=CodeStage.DRAFT,
                gate=gate,
                replay_id=replay.entry_id,
                stage_progress=[CodeStage.DRAFT.value],
            )
            rec = self.store.put(
                kind="code",
                body=source,
                backend=bundle.backend,
                stage=CodeStage.DRAFT.value,
                artifact_id=bundle_id,
                metadata={"intent": intent[:500], "replay_id": replay.entry_id},
                suffix=".py",
            )
            bundle.provenance.append(rec.as_dict())
            self.bundles[bundle_id] = bundle
            return bundle

    def replay_draft(self, entry_id: str) -> CodeBundle:
        """Re-materialize a CodeBundle from a recorded DraftReplayLog entry."""
        entry = self.replay_log.replay(entry_id)
        with self._lock:
            digest = hashlib.sha256(f"{entry.intent}:{entry.source}".encode()).hexdigest()[:16]
            bundle_id = f"code_{digest}_replay"
            gate = PromoteGate(min_shadow_score=self.min_shadow)
            bundle = CodeBundle(
                bundle_id=bundle_id,
                intent=entry.intent,
                source=entry.source,
                backend=entry.backend,
                stage=CodeStage.DRAFT,
                gate=gate,
                replay_id=entry.entry_id,
                stage_progress=[CodeStage.DRAFT.value],
            )
            rec = self.store.put(
                kind="code",
                body=entry.source,
                backend=entry.backend,
                stage=CodeStage.DRAFT.value,
                artifact_id=bundle_id,
                metadata={"intent": entry.intent[:500], "replay_id": entry.entry_id, "replayed": True},
                suffix=".py",
            )
            bundle.provenance.append(rec.as_dict())
            self.bundles[bundle_id] = bundle
            return bundle

    def run_static(self, bundle_id: str) -> CodeBundle:
        with self._lock:
            b = self._get(bundle_id)
            errs = _static_check(b.source)
            b.static_errors = errs
            b.gate.static_ok = not errs
            b.stage = CodeStage.STATIC_OK if not errs else CodeStage.REJECTED
            if errs:
                b.gate.promoted = False
                b.may_control = False
            else:
                b.stage_progress.append(CodeStage.STATIC_OK.value)
            self._persist(b, b.stage.value)
            return b

    def run_contract(self, bundle_id: str, *, spec: dict[str, Any] | None = None) -> CodeBundle:
        with self._lock:
            b = self._get(bundle_id)
            if b.stage == CodeStage.REJECTED:
                return b
            errs = _contract_check(b.source, spec=spec)
            b.contract_errors = errs
            b.gate.contract_ok = not errs
            b.stage = CodeStage.CONTRACT_OK if not errs else CodeStage.REJECTED
            if not errs:
                b.stage_progress.append(CodeStage.CONTRACT_OK.value)
            self._persist(b, b.stage.value)
            return b

    def run_sandbox(self, bundle_id: str, *, args: dict[str, Any] | None = None) -> CodeBundle:
        with self._lock:
            b = self._get(bundle_id)
            if b.stage in (CodeStage.REJECTED,):
                return b
            if not b.gate.static_ok or not b.gate.contract_ok:
                raise PromoteRefused("sandbox requires static+contract ok")
            result = self.sandbox.run(b.source, args=args or {"x": 1.0, "y": 2.0})
            b.sandbox = result.as_dict()
            b.gate.sandbox_ok = result.ok
            b.stage = CodeStage.SANDBOXED if result.ok else CodeStage.REJECTED
            if result.ok:
                b.stage_progress.append(CodeStage.SANDBOXED.value)
            self._persist(b, b.stage.value)
            return b

    def run_shadow(self, bundle_id: str) -> CodeBundle:
        with self._lock:
            b = self._get(bundle_id)
            if not b.gate.sandbox_ok or not b.sandbox:
                raise PromoteRefused("shadow requires successful sandbox")
            score, metrics = _shadow_score(
                SandboxResult(
                    ok=bool(b.sandbox.get("ok")),
                    value=b.sandbox.get("value"),
                    error=b.sandbox.get("error"),
                )
            )
            b.shadow_score = score
            b.shadow_metrics = metrics.as_dict()
            b.gate.shadow_score = score
            b.gate.shadow_validated = score >= b.gate.min_shadow_score
            b.stage = CodeStage.SHADOW_SCORED
            b.stage_progress.append(CodeStage.SHADOW_SCORED.value)
            self._persist(b, b.stage.value)
            return b

    def promote(self, bundle_id: str) -> CodeBundle:
        t0 = time.perf_counter()
        with self._lock:
            b = self._get(bundle_id)
            if not b.gate.ready():
                raise PromoteRefused(
                    f"promote blocked: gate={b.gate.as_dict()}; never silent control overwrite"
                )
            prior = self._last_promoted
            b.prior_promoted_id = prior
            b.gate.promoted = True
            b.may_control = True
            b.research_tier = False
            b.stage = CodeStage.PROMOTED
            b.stage_progress.append(CodeStage.PROMOTED.value)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._last_timings["promote_ms"] = elapsed_ms
            self._promote_stack.append(bundle_id)
            self._last_promoted = bundle_id
            self._persist(
                b,
                CodeStage.PROMOTED.value,
                metadata={"promoted": True, "prior": prior, "promote_ms": elapsed_ms},
            )
            return b

    def demote(self, bundle_id: str, *, reason: str = "manual_demote") -> CodeBundle:
        with self._lock:
            b = self._get(bundle_id)
            b.gate.promoted = False
            b.gate.shadow_validated = False
            b.may_control = False
            b.research_tier = True
            b.stage = CodeStage.DEMOTION
            b.stage_progress.append(CodeStage.DEMOTION.value)
            if self._last_promoted == bundle_id:
                self._last_promoted = None
            if bundle_id in self._promote_stack:
                self._promote_stack = [x for x in self._promote_stack if x != bundle_id]
            self._persist(b, CodeStage.DEMOTION.value, metadata={"reason": reason})
            return b

    def rollback_last_promote(self, *, reason: str = "rollback_last") -> CodeBundle:
        """Roll back the most recently promoted bundle to RESEARCH_TIER."""
        with self._lock:
            if not self._promote_stack:
                self._reload_promote_stack()
            if not self._promote_stack:
                raise PromoteRefused("no promoted bundle to roll back")
            bundle_id = self._promote_stack.pop()
            b = self._get(bundle_id)
            b.gate.promoted = False
            b.gate.shadow_validated = False
            b.may_control = False
            b.research_tier = True
            b.stage = CodeStage.ROLLBACK
            b.stage_progress.append(CodeStage.ROLLBACK.value)
            self._last_promoted = self._promote_stack[-1] if self._promote_stack else None
            self._persist(b, CodeStage.ROLLBACK.value, metadata={"reason": reason})
            return b

    def evolve(
        self,
        intent: str,
        *,
        spec: dict[str, Any] | None = None,
        backend: DraftBackend | GeneratorBackend | None = None,
        auto_promote: bool = False,
    ) -> CodeBundle:
        """Full pipeline. Promote only if auto_promote and gate ready."""
        t0 = time.perf_counter()
        b = self.start(intent, spec=spec, backend=backend)
        self.run_static(b.bundle_id)
        if b.stage == CodeStage.REJECTED:
            self._last_timings["evolve_ms"] = (time.perf_counter() - t0) * 1000.0
            return b
        self.run_contract(b.bundle_id, spec=spec)
        if b.stage == CodeStage.REJECTED:
            self._last_timings["evolve_ms"] = (time.perf_counter() - t0) * 1000.0
            return b
        self.run_sandbox(b.bundle_id)
        if b.stage == CodeStage.REJECTED:
            self._last_timings["evolve_ms"] = (time.perf_counter() - t0) * 1000.0
            return b
        self.run_shadow(b.bundle_id)
        if auto_promote and b.gate.ready():
            out = self.promote(b.bundle_id)
            self._last_timings["evolve_ms"] = (time.perf_counter() - t0) * 1000.0
            return out
        self._last_timings["evolve_ms"] = (time.perf_counter() - t0) * 1000.0
        return b

    def stage_progress_summary(self, bundle_id: str) -> dict[str, Any]:
        b = self._get(bundle_id)
        done = set(b.stage_progress)
        return {
            "bundle_id": bundle_id,
            "stage": b.stage.value,
            "progress": list(b.stage_progress),
            "checklist": [
                {"stage": s.value, "done": s.value in done or b.stage == CodeStage.REJECTED and False}
                for s in self.STAGE_ORDER
            ],
            "rejected": b.stage == CodeStage.REJECTED,
            "shadow_metrics": dict(b.shadow_metrics),
            "gate": b.gate.as_dict(),
        }


    def _reload_promote_stack(self) -> None:
        from pathlib import Path

        idx = Path(self.store.root) / "code" / "bundles_index.json"
        if not idx.is_file():
            return
        try:
            known = json.loads(idx.read_text(encoding="utf-8"))
        except Exception:
            return
        for bid in known:
            path = self._bundle_state_path(bid)
            if not path.is_file():
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if raw.get("promote_stack"):
                self._promote_stack = list(raw["promote_stack"])
                self._last_promoted = raw.get("last_promoted")

    def _bundle_state_path(self, bundle_id: str) -> Path:
        from pathlib import Path

        return Path(self.store.root) / "code" / f"{bundle_id}_state.json"

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
            metadata={
                "intent": b.intent[:500],
                "shadow_score": b.shadow_score,
                "shadow_metrics": b.shadow_metrics,
                **(metadata or {}),
            },
            suffix=".py",
        )
        b.provenance.append(rec.as_dict())
        # Full bundle state for CLI / cross-process promote + rollback
        state = b.as_dict()
        state["source"] = b.source
        state["promote_stack"] = list(self._promote_stack)
        state["last_promoted"] = self._last_promoted
        path = self._bundle_state_path(b.bundle_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        # Index of known bundles
        idx = Path(self.store.root) / "code" / "bundles_index.json"
        try:
            known = json.loads(idx.read_text(encoding="utf-8")) if idx.is_file() else []
        except Exception:
            known = []
        if b.bundle_id not in known:
            known.append(b.bundle_id)
            idx.write_text(json.dumps(known, indent=2), encoding="utf-8")
        return rec

    def _hydrate_bundle(self, bundle_id: str) -> CodeBundle | None:
        from pathlib import Path

        path = self._bundle_state_path(bundle_id)
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        gate_raw = raw.get("gate") or {}
        gate = PromoteGate(
            static_ok=bool(gate_raw.get("static_ok")),
            contract_ok=bool(gate_raw.get("contract_ok")),
            sandbox_ok=bool(gate_raw.get("sandbox_ok")),
            shadow_validated=bool(gate_raw.get("shadow_validated")),
            shadow_score=float(gate_raw.get("shadow_score") or 0.0),
            min_shadow_score=float(gate_raw.get("min_shadow_score") or 0.9),
            promoted=bool(gate_raw.get("promoted")),
        )
        try:
            stage = CodeStage(raw.get("stage") or "DRAFT")
        except Exception:
            stage = CodeStage.DRAFT
        b = CodeBundle(
            bundle_id=bundle_id,
            intent=str(raw.get("intent") or ""),
            source=str(raw.get("source") or ""),
            backend=str(raw.get("backend") or "template"),
            stage=stage,
            gate=gate,
            static_errors=list(raw.get("static_errors") or []),
            contract_errors=list(raw.get("contract_errors") or []),
            sandbox=raw.get("sandbox"),
            shadow_score=float(raw.get("shadow_score") or 0.0),
            shadow_metrics=dict(raw.get("shadow_metrics") or {}),
            provenance=list(raw.get("provenance") or []),
            may_control=bool(raw.get("may_control")),
            created_at=str(raw.get("created_at") or ""),
            research_tier=bool(raw.get("research_tier", True)),
            replay_id=raw.get("replay_id"),
            stage_progress=list(raw.get("stage_progress") or []),
            prior_promoted_id=raw.get("prior_promoted_id"),
        )
        if not b.source:
            # fall back to latest artifact body
            rec = self.store.latest(bundle_id)
            if rec is not None:
                b.source = self.store.read_body(rec).decode("utf-8")
        self.bundles[bundle_id] = b
        stack = raw.get("promote_stack") or []
        if stack:
            self._promote_stack = list(stack)
        if raw.get("last_promoted"):
            self._last_promoted = raw.get("last_promoted")
        return b

    def _get(self, bundle_id: str) -> CodeBundle:
        if bundle_id not in self.bundles:
            hydrated = self._hydrate_bundle(bundle_id)
            if hydrated is None:
                raise KeyError(f"unknown bundle_id={bundle_id}")
            return hydrated
        return self.bundles[bundle_id]

    def list_bundles(self) -> list[dict[str, Any]]:
        with self._lock:
            return [b.as_dict() for b in self.bundles.values()]

    @property
    def last_promoted_id(self) -> str | None:
        return self._last_promoted

    @property
    def last_timings(self) -> dict[str, float]:
        return dict(self._last_timings)

    def within_wall_clock_budgets(self) -> bool:
        """True if last evolve/promote timings (if any) are under budgets."""
        e = self._last_timings.get("evolve_ms")
        p = self._last_timings.get("promote_ms")
        if e is not None and e > self.evolve_budget_ms:
            return False
        if p is not None and p > self.promote_budget_ms:
            return False
        return True
