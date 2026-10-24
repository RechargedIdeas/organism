"""Artifact H — ImmuneLayer. Decisions via FULL/affects_control workspace bindings only."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from organism_sdk.hypervector import Hypervector
from organism_sdk.trace import ImmuneTraceEntry, TraceEmitter
from organism_sdk.workspace import BindingRecord, WorkspaceClient

Decision = Literal["PASS", "QUARANTINE", "DEMOTE", "SURVEIL", "TOLERATE"]
Classification = Literal["SELF", "PAMP", "DANGER", "SAFE"]
IMMUNE_TAG = "immune_decision"
IMMUNE_MODULE_ID = "immune_layer"


@dataclass
class MemoryCell:
    cell_id: str
    signature: Hypervector
    response_history: list[dict[str, Any]] = field(default_factory=list)
    last_match_at: datetime | None = None

    def record(self, action: str, success: bool, recovery_s: float) -> None:
        self.response_history.append({"action": action, "success": success, "recovery_s": recovery_s})
        self.last_match_at = datetime.now(timezone.utc)


@dataclass
class ImmuneDecision:
    decision: Decision
    classification: Classification
    antigen_score: float
    source_module_id: str = ""
    memory_cell_id: str | None = None
    binding_key: str = IMMUNE_TAG
    remembered: bool = False
    latency_ms: float = 0.0

    def as_payload(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "classification": self.classification,
            "antigen_score": self.antigen_score,
            "source_module_id": self.source_module_id,
            "memory_cell_id": self.memory_cell_id,
            "remembered": self.remembered,
            "latency_ms": self.latency_ms,
            "salience": {"fidelity": "FULL"},
            "safety": {"affects_control": True},
        }


class ImmuneLayer:
    def __init__(
        self,
        workspace: WorkspaceClient,
        *,
        trace: TraceEmitter | None = None,
        antigen_threshold: float = 0.48,
        memory_threshold: float = 0.85,
        role_seed: int = 0x494D4D55,
    ) -> None:
        self._ws = workspace
        self._trace = trace
        self.antigen_threshold = antigen_threshold
        self.memory_threshold = memory_threshold
        self._lock = threading.RLock()
        self._self_profile: list[Hypervector] = []
        self._detectors: list[Hypervector] = []
        self._memory: list[MemoryCell] = []
        self._role = Hypervector.random(seed=role_seed)
        self._direct_lifecycle_calls = 0
        for i in range(8):
            self._detectors.append(Hypervector.random(seed=role_seed + 17 + i))

    @property
    def direct_lifecycle_calls(self) -> int:
        return self._direct_lifecycle_calls

    def learn_self(self, hv: Hypervector) -> None:
        with self._lock:
            self._self_profile.append(hv)

    def add_memory_cell(self, signature: Hypervector, *, action: str = "QUARANTINE") -> MemoryCell:
        cell = MemoryCell(cell_id=str(uuid.uuid4()), signature=signature)
        cell.record(action, True, 1.0)
        with self._lock:
            self._memory.append(cell)
        return cell

    def _self_similarity(self, hv: Hypervector) -> float:
        if not self._self_profile:
            return 0.5
        return max(s.similarity(hv) for s in self._self_profile)

    def _detector_hit(self, hv: Hypervector) -> float:
        if not self._detectors:
            return 0.0
        return max(d.similarity(hv) for d in self._detectors)

    def _memory_match(self, hv: Hypervector) -> MemoryCell | None:
        best, best_s = None, 0.0
        for cell in self._memory:
            s = cell.signature.similarity(hv)
            if s > best_s:
                best_s, best = s, cell
        return best if best is not None and best_s >= self.memory_threshold else None

    def ingress(
        self,
        antigen: Hypervector,
        *,
        source_module_id: str = "",
        cortisol: float = 0.0,
        melatonin: float = 0.0,
    ) -> ImmuneDecision:
        t0 = time.perf_counter()
        tolerance = max(0.35, min(0.85, self.antigen_threshold + 0.15 * cortisol - 0.1 * melatonin))
        self_sim = self._self_similarity(antigen)
        det = self._detector_hit(antigen)
        antigen_score = det if not self._self_profile else max(0.0, det - 0.5 * self_sim)

        if self._self_profile and self_sim >= 0.85:
            decision = ImmuneDecision("PASS", "SELF", antigen_score, source_module_id)
        elif antigen_score < tolerance:
            decision = ImmuneDecision("TOLERATE", "SAFE", antigen_score, source_module_id)
            self.learn_self(antigen)
        else:
            mem = self._memory_match(antigen)
            if mem is not None:
                action = mem.response_history[-1]["action"] if mem.response_history else "QUARANTINE"
                if cortisol >= 0.5 and action == "DEMOTE":
                    action = "QUARANTINE"
                if action not in ("QUARANTINE", "DEMOTE", "SURVEIL"):
                    action = "QUARANTINE"
                decision = ImmuneDecision(action, "PAMP", antigen_score, source_module_id, mem.cell_id, remembered=True)  # type: ignore[arg-type]
                mem.record(decision.decision, True, 0.1)
            else:
                decision = ImmuneDecision(
                    "QUARANTINE" if cortisol >= 0.5 else "SURVEIL",
                    "DANGER",
                    antigen_score,
                    source_module_id,
                )
                cell = self.add_memory_cell(antigen, action=decision.decision)
                decision.memory_cell_id = cell.cell_id

        decision.latency_ms = (time.perf_counter() - t0) * 1000.0
        binding = self._write_decision(decision)
        if self._trace is not None:
            self._trace.emit_immune(
                ImmuneTraceEntry(
                    decision=decision.decision,
                    antigen_score=decision.antigen_score,
                    classification=decision.classification,
                    source_module_id=source_module_id,
                    binding_key=str(binding.binding_id),
                )
            )
        return decision

    def _write_decision(self, decision: ImmuneDecision) -> BindingRecord:
        filler = Hypervector.random()
        hv = self._role.bind(filler)
        rec = BindingRecord(
            binding_id=uuid.uuid4(),
            hypervector=hv,
            role=self._role,
            filler=filler,
            tags=(IMMUNE_TAG, f"immune_decision/{decision.decision.lower()}"),
            module_id=IMMUNE_MODULE_ID,
            salience=1.0,
            fidelity="FULL",
            payload=decision.as_payload(),
            affects_control=True,
        )
        result = self._ws.write(rec)
        if result.status != "ACCEPTED":
            raise RuntimeError(f"immune write rejected: {result.reason_code}")
        got = self._ws.read_by_binding_id(rec.binding_id)
        assert got is not None
        return got

    def deregister(self, *_a: Any, **_k: Any) -> None:
        self._direct_lifecycle_calls += 1
        raise PermissionError("IM-2: ImmuneLayer must not call registry lifecycle APIs")


def validate_control_binding(rec: BindingRecord) -> bool:
    """Return True iff binding is a trustworthy immune control decision (IMP-21)."""
    if "immune_decision" not in rec.tags and not any(
        t.startswith("immune_decision/") for t in rec.tags
    ):
        return False
    return (
        rec.module_id == IMMUNE_MODULE_ID
        and rec.fidelity == "FULL"
        and rec.affects_control
        and rec.salience >= 1.0
        and isinstance(rec.payload, dict)
        and rec.payload.get("safety", {}).get("affects_control") is True
    )
