"""Artifact I — Apoptosis / extended lifecycle."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from organism_sdk.contract import ReliabilityTier, SubstrateContract
from organism_sdk.hypervector import Hypervector
from organism_sdk.trace import LifecycleTraceEntry, TraceEmitter
from organism_sdk.workspace import BindingRecord, WorkspaceClient

ExtendedLifecycle = Literal[
    "PROPOSED", "SANDBOXED", "SHADOW_VALIDATED", "EXPLORATION", "DEVELOPMENT",
    "DELIBERATION", "SELF_TERMINATING", "SUCCEEDED", "DEGRADED", "DEPRECATED", "RETIRED",
]
DEATH_CERT_TAG = "death_certificate"
SYNTHETIC_DRAIN_TAG = "lifecycle_synthetic"


@dataclass
class DeathCertificate:
    module_id: str
    cause: str
    memory_export_digest: str
    successor_spec: dict[str, Any] | None = None
    decisions_sample: list[dict[str, Any]] = field(default_factory=list)
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "cause": self.cause,
            "memory_export_digest": self.memory_export_digest,
            "successor_spec": self.successor_spec,
            "decisions_sample": self.decisions_sample,
            "issued_at": self.issued_at.isoformat(),
        }


@dataclass
class MemoryExport:
    weights_summary: dict[str, Any]
    decision_history: list[dict[str, Any]]
    failure_modes: list[str]
    calibration: dict[str, Any]

    def digest(self) -> str:
        body = json.dumps(
            {
                "weights_summary": self.weights_summary,
                "decision_history": self.decision_history,
                "failure_modes": self.failure_modes,
                "calibration": self.calibration,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(body).hexdigest()


class ApoptosisError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def assert_self_termination_allowed(contract: SubstrateContract) -> None:
    if contract.safety.reliability_tier == ReliabilityTier.T0_DETERMINISTIC:
        raise ApoptosisError("AP-2", "T0 modules never self-terminate")
    if not getattr(contract.lifecycle, "self_termination_permitted", False):
        raise ApoptosisError("AP-1", "self_termination_permitted must be true")


@dataclass
class SelfTerminateResult:
    accepted: bool
    state: ExtendedLifecycle
    death_certificate: DeathCertificate | None = None
    reason: str | None = None
    drain_outcome: str | None = None  # completed | abandoned | killed
    synthetic_lifecycle_recorded: bool = False


@dataclass
class ShadowValidateResult:
    passed: bool
    successor_id: str
    against_module_id: str
    pass_rate: float
    promotion_blocked: bool
    reason: str = ""


@dataclass
class PromoteResult:
    promoted: bool
    state: ExtendedLifecycle
    reason: str = ""


class ApoptosisService:
    def __init__(
        self,
        workspace: WorkspaceClient,
        *,
        trace: TraceEmitter | None = None,
        role_seed: int = 0x41504F50,
    ) -> None:
        self._ws = workspace
        self._trace = trace
        self._role = Hypervector.random(seed=role_seed)
        self._states: dict[str, ExtendedLifecycle] = {}
        self._certificates: dict[str, DeathCertificate] = {}
        self._shadow_ok: dict[str, bool] = {}
        self._synthetic_records: list[dict[str, Any]] = []

    def current_state(self, module_id: str) -> ExtendedLifecycle | None:
        return self._states.get(module_id)

    @property
    def synthetic_lifecycle_records(self) -> list[dict[str, Any]]:
        return list(self._synthetic_records)

    def begin_self_terminate(
        self,
        contract: SubstrateContract,
        *,
        cause: str,
        memory: MemoryExport,
        successor_available: bool,
        control_affecting: bool,
        from_state: ExtendedLifecycle = "DELIBERATION",
        drain_killed_mid_export: bool = False,
        successor_spec: dict[str, Any] | None = None,
    ) -> SelfTerminateResult:
        try:
            assert_self_termination_allowed(contract)
        except ApoptosisError as exc:
            if self._trace:
                self._trace.emit_lifecycle(
                    LifecycleTraceEntry(
                        module_id=contract.identity.module_id,
                        from_state=from_state,
                        to_state=from_state,
                        event=f"self_terminate_rejected:{exc.code}",
                    )
                )
            return SelfTerminateResult(False, from_state, reason=exc.code)

        mid = contract.identity.module_id
        if control_affecting and not successor_available:
            self._states[mid] = "DEGRADED"
            if self._trace:
                self._trace.emit_lifecycle(
                    LifecycleTraceEntry(
                        module_id=mid,
                        from_state=from_state,
                        to_state="DEGRADED",
                        event="self_terminate_no_successor",
                    )
                )
            return SelfTerminateResult(False, "DEGRADED", reason="AP-3")

        self._states[mid] = "SELF_TERMINATING"
        if self._trace:
            self._trace.emit_lifecycle(
                LifecycleTraceEntry(
                    module_id=mid,
                    from_state=from_state,
                    to_state="SELF_TERMINATING",
                    event="self_terminating",
                    on_drain_outcome="started",
                )
            )

        # N4: drain killed mid-export — runtime writes synthetic lifecycle; no SUCCEEDED
        if drain_killed_mid_export:
            synth = {
                "module_id": mid,
                "event": "DRAIN_COMPLETED",
                "on_drain_outcome": "killed",
                "cause": cause,
                "synthetic": True,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            self._write_synthetic(synth)
            self._synthetic_records.append(synth)
            if self._trace:
                self._trace.emit_lifecycle(
                    LifecycleTraceEntry(
                        module_id=mid,
                        from_state="SELF_TERMINATING",
                        to_state="SELF_TERMINATING",
                        event="drain_killed_mid_export",
                        on_drain_outcome="killed",
                        on_drain_synthetic=True,
                    )
                )
            return SelfTerminateResult(
                False,
                "SELF_TERMINATING",
                reason="N4",
                drain_outcome="killed",
                synthetic_lifecycle_recorded=True,
            )

        spec = successor_spec or (
            {"mode": "EXPLORATION", "inherit_memory": True} if successor_available else None
        )
        cert = DeathCertificate(
            module_id=mid,
            cause=cause,
            memory_export_digest=memory.digest(),
            successor_spec=spec,
            decisions_sample=list(memory.decision_history[-5:]),
        )
        self._write_certificate(cert)
        self._certificates[mid] = cert
        if not cert.memory_export_digest:
            return SelfTerminateResult(False, "SELF_TERMINATING", cert, "AP-5")
        self._states[mid] = "SUCCEEDED"
        if self._trace:
            self._trace.emit_lifecycle(
                LifecycleTraceEntry(
                    module_id=mid,
                    from_state="SELF_TERMINATING",
                    to_state="SUCCEEDED",
                    event="succeeded",
                    on_drain_outcome="completed",
                )
            )
        # Successor enters EXPLORATION pending shadow-validate (N1 / N5)
        if successor_available and spec is not None:
            sid = str(spec.get("successor_id", f"{mid}__successor"))
            self._states[sid] = "EXPLORATION"
            self._shadow_ok[sid] = False
        return SelfTerminateResult(True, "SUCCEEDED", cert, drain_outcome="completed")

    def _write_synthetic(self, payload: dict[str, Any]) -> BindingRecord:
        filler = Hypervector.random()
        hv = self._role.bind(filler)
        rec = BindingRecord(
            binding_id=uuid.uuid4(),
            hypervector=hv,
            role=self._role,
            filler=filler,
            tags=(SYNTHETIC_DRAIN_TAG, f"lifecycle_synthetic/{payload['module_id']}"),
            module_id=payload["module_id"],
            salience=1.0,
            fidelity="FULL",
            payload=payload,
            affects_control=True,
        )
        result = self._ws.write(rec)
        if result.status != "ACCEPTED":
            raise RuntimeError(f"synthetic lifecycle write rejected: {result.reason_code}")
        got = self._ws.read_by_binding_id(rec.binding_id)
        assert got is not None
        return got

    def _write_certificate(self, cert: DeathCertificate) -> BindingRecord:
        filler = Hypervector.random()
        hv = self._role.bind(filler)
        rec = BindingRecord(
            binding_id=uuid.uuid4(),
            hypervector=hv,
            role=self._role,
            filler=filler,
            tags=(DEATH_CERT_TAG, f"death_certificate/{cert.module_id}"),
            module_id=cert.module_id,
            salience=1.0,
            fidelity="FULL",
            payload=cert.as_dict(),
            affects_control=True,
        )
        result = self._ws.write(rec)
        if result.status != "ACCEPTED":
            raise RuntimeError(f"DeathCertificate write rejected: {result.reason_code}")
        got = self._ws.read_by_binding_id(rec.binding_id)
        assert got is not None
        return got

    def shadow_validate_successor(
        self,
        successor_id: str,
        against_module_id: str,
        *,
        pass_rate: float,
        decisions: list[dict[str, Any]] | None = None,
    ) -> ShadowValidateResult:
        """Compare successor decisions against DeathCertificate sample. Fail blocks promotion (N5)."""
        cert = self._certificates.get(against_module_id)
        if cert is None:
            self._shadow_ok[successor_id] = False
            self._states[successor_id] = self._states.get(successor_id, "EXPLORATION")
            return ShadowValidateResult(
                False, successor_id, against_module_id, pass_rate, True, reason="no_death_certificate"
            )

        sample = cert.decisions_sample
        if decisions is not None and sample:
            # Match by id when present; otherwise require pass_rate only
            sample_ids = {d.get("id") for d in sample if "id" in d}
            if sample_ids:
                matched = sum(1 for d in decisions if d.get("id") in sample_ids)
                rate = matched / max(1, len(sample_ids))
                pass_rate = min(pass_rate, rate)

        ok = pass_rate >= 0.9
        self._shadow_ok[successor_id] = ok
        if not ok:
            self._states[successor_id] = "EXPLORATION"
            if self._trace:
                self._trace.emit_lifecycle(
                    LifecycleTraceEntry(
                        module_id=successor_id,
                        from_state="EXPLORATION",
                        to_state="EXPLORATION",
                        event="shadow_validate_failed",
                    )
                )
            return ShadowValidateResult(
                False, successor_id, against_module_id, pass_rate, True, reason="shadow_validate_failed"
            )

        self._states[successor_id] = "SHADOW_VALIDATED"
        if self._trace:
            self._trace.emit_lifecycle(
                LifecycleTraceEntry(
                    module_id=successor_id,
                    from_state="EXPLORATION",
                    to_state="SHADOW_VALIDATED",
                    event="shadow_validate_passed",
                )
            )
        return ShadowValidateResult(
            True, successor_id, against_module_id, pass_rate, False, reason="ok"
        )

    def promote_successor(
        self, successor_id: str, *, to_state: ExtendedLifecycle = "DELIBERATION"
    ) -> PromoteResult:
        """Promotion only after successful shadow-validate against DeathCertificate."""
        if not self._shadow_ok.get(successor_id, False):
            return PromoteResult(False, self._states.get(successor_id, "EXPLORATION"), "promotion_blocked")
        if self._states.get(successor_id) not in ("SHADOW_VALIDATED", "EXPLORATION"):
            return PromoteResult(False, self._states.get(successor_id, "EXPLORATION"), "invalid_state")
        self._states[successor_id] = to_state
        if self._trace:
            self._trace.emit_lifecycle(
                LifecycleTraceEntry(
                    module_id=successor_id,
                    from_state="SHADOW_VALIDATED",
                    to_state=to_state,
                    event="successor_promoted",
                )
            )
        return PromoteResult(True, to_state, "ok")
