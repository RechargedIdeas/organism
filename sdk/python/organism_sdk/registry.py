"""RegistryClient — A3.1; M1 in-process mock registry."""
from __future__ import annotations

import hashlib
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from organism_sdk.contract import (
    ModuleRole,
    ReliabilityTier,
    Severity,
    SubstrateContract,
    ValidationIssue,
)
from organism_sdk.errors import RegistrationRejected
from organism_sdk.evidence import (
    CALIBRATED_TIERS,
    CalibrationRecord,
    CalibrationThreshold,
    MeasuredMetabolics,
    MetabolicTolerance,
    calibration_gate,
    metabolic_gate,
)
from organism_sdk.health import HealthReport
from organism_sdk.signing import TrustStore, promotion_payload, registration_payload, verify_any
from organism_sdk.trace import LifecycleTraceEntry, TraceEmitter

LifecycleState = Literal[
    "PROPOSED",
    "SANDBOXED",
    "SHADOW_VALIDATED",
    "EXPLORATION",
    "DEVELOPMENT",
    "DELIBERATION",
    "SELF_TERMINATING",
    "SUCCEEDED",
    "DEGRADED",
    "DEPRECATED",
    "RETIRED",
]

# Linear promotion ladder (v0.1). DEVELOPMENT is EXPLORATION-subset.
_PROMOTE_ORDER = [
    "PROPOSED",
    "SANDBOXED",
    "SHADOW_VALIDATED",
    "EXPLORATION",
    "DELIBERATION",
    "DEPRECATED",
    "RETIRED",
]
_EXTENDED_STATES = frozenset({"DEVELOPMENT", "SELF_TERMINATING", "SUCCEEDED", "DEGRADED"})


@dataclass
class ModuleHandle:
    module_id: str
    version: str
    role: ModuleRole
    tier: ReliabilityTier
    state: LifecycleState
    contract_digest: bytes
    hardware_requirement: str = "NONE"  # IMP-17


@dataclass
class RegisterResponse:
    module_id: str
    initial_state: LifecycleState
    validation_issues: list[ValidationIssue] = field(default_factory=list)


@dataclass
class PromoteResponse:
    accepted: bool
    validation_issues: list[ValidationIssue] = field(default_factory=list)


@dataclass
class HotSwapResponse:
    accepted: bool
    validation_issues: list[ValidationIssue] = field(default_factory=list)


@dataclass
class CapabilityFilter:
    roles: tuple[ModuleRole, ...] = ()
    min_reliability: ReliabilityTier | None = None
    min_lifecycle_state: LifecycleState | None = None


@dataclass
class ShadowValidationRecord:
    invocations: int
    incumbent_error: float
    candidate_error: float
    p95_latency_ms: float
    gates_passed: tuple[str, ...] = ()
    evidence_digest: bytes = b""


# States a module may enter only with shadow evidence that meets the threshold (gap B1): the states where it is
# validated or serves. PROPOSED -> SANDBOXED needs no evidence, and DEPRECATED and RETIRED are retirements.
GATED_STATES: frozenset[str] = frozenset({"SHADOW_VALIDATED", "EXPLORATION", "DELIBERATION"})


@dataclass(frozen=True)
class ShadowThreshold:
    """What shadow evidence must show before a gated promotion.

    ``min_invocations`` counts the live invocations over all records. ``max_error_ratio`` bounds the
    weighted candidate error by the weighted incumbent error; 1.0 means no worse than the incumbent.
    """

    min_invocations: int = 100
    max_error_ratio: float = 1.0


def shadow_gate(records: Sequence[ShadowValidationRecord], threshold: ShadowThreshold) -> list[ValidationIssue]:
    """The issues that stop a gated promotion, or an empty list when the evidence passes. Pure.

    Codes: ``shadow_evidence_insufficient`` (no records, or too few invocations),
    ``shadow_evidence_unattributed`` (a record without an evidence digest), ``shadow_error_regression``.
    """
    if not records:
        return [ValidationIssue(Severity.ERROR, "shadow_evidence_insufficient", "shadow_records", "no shadow records")]
    total = sum(r.invocations for r in records)
    if total < threshold.min_invocations:
        return [
            ValidationIssue(
                Severity.ERROR,
                "shadow_evidence_insufficient",
                "shadow_records",
                f"invocations={total} required={threshold.min_invocations}",
            )
        ]
    if any(not r.evidence_digest for r in records):
        return [
            ValidationIssue(
                Severity.ERROR, "shadow_evidence_unattributed", "shadow_records", "a record has no evidence digest"
            )
        ]
    # Explicit loops: Python 3.12+ compensates float sums, and the Kotlin port adds plainly. Both must agree.
    incumbent = 0.0
    candidate = 0.0
    for r in records:
        incumbent += r.incumbent_error * r.invocations
        candidate += r.candidate_error * r.invocations
    if candidate > threshold.max_error_ratio * incumbent:
        return [
            ValidationIssue(
                Severity.ERROR, "shadow_error_regression", "shadow_records", "candidate error exceeds the incumbent"
            )
        ]
    return []


@dataclass
class _Entry:
    contract: SubstrateContract
    state: LifecycleState
    artifact_digest: bytes
    module: Any = None
    contract_digest: bytes = b""


_TIER_RANK = {
    ReliabilityTier.T0_DETERMINISTIC: 0,
    ReliabilityTier.T1_CALIBRATED_NONLEARNED: 1,
    ReliabilityTier.T2_LEARNED_CALIBRATED: 2,
    ReliabilityTier.T3_LEARNED_UNCALIBRATED: 3,
}


def _bad_signature(field_path: str, role: str) -> ValidationIssue:
    return ValidationIssue(
        Severity.ERROR,
        "signature_invalid",
        field_path,
        f"no trusted {role} key verifies this signature",
    )


class RegistryClient:
    """In-process registry for M1. Validates contracts, stores modules, probes health.

    With a ``trust_store``, registration needs an author signature and promotion needs an approver
    signature, each from a trusted key. Without one, signatures are not checked. That is the
    default for local development and for the internal callers that pass placeholder bytes.

    A promotion into a ``GATED_STATES`` state needs shadow evidence that meets ``shadow_threshold``
    whether or not a trust store is set. ``test_bypass_validation`` does not skip that check.

    For a gated promotion, calibration and measurement evidence is checked when it is supplied. Two switches make it
    required: ``require_calibration`` makes a calibrated tier (T1, T2) show a calibration record, and
    ``require_measurement`` makes every gated promotion show a measured metabolic record. Both default to off.
    """

    def __init__(
        self,
        trace: TraceEmitter | None = None,
        *,
        trust_store: TrustStore | None = None,
        shadow_threshold: ShadowThreshold | None = None,
        require_calibration: bool = False,
        require_measurement: bool = False,
        calibration_threshold: CalibrationThreshold | None = None,
        metabolic_tolerance: MetabolicTolerance | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._modules: dict[str, _Entry] = {}
        self._trace = trace or TraceEmitter()
        self._audit: list[dict[str, Any]] = []
        self._trust_store = trust_store
        self._shadow_threshold = shadow_threshold if shadow_threshold is not None else ShadowThreshold()
        self._require_calibration = require_calibration
        self._require_measurement = require_measurement
        self._calibration_threshold = (
            calibration_threshold if calibration_threshold is not None else CalibrationThreshold()
        )
        self._metabolic_tolerance = metabolic_tolerance if metabolic_tolerance is not None else MetabolicTolerance()

    def _note_rejected(self, role: str, module_id: str) -> None:
        with self._lock:
            self._audit.append(
                {
                    "event": "signature_rejected",
                    "module_id": module_id,
                    "role": role,
                    "at": datetime.now(UTC).isoformat(),
                }
            )

    def register(
        self,
        contract: SubstrateContract,
        artifact_digest: bytes,
        author_signature: bytes,
        *,
        module: Any = None,
        initial_state: LifecycleState = "PROPOSED",
        test_bypass_promote: LifecycleState | None = None,
    ) -> RegisterResponse:
        issues = contract.validate()
        errors = [i for i in issues if i.severity == Severity.ERROR]
        if errors:
            raise RegistrationRejected(errors)

        if self._trust_store is not None and not verify_any(
            self._trust_store.authors,
            author_signature,
            registration_payload(
                contract.identity.module_id, contract.identity.version, artifact_digest
            ),
        ):
            self._note_rejected("author", contract.identity.module_id)
            raise RegistrationRejected([_bad_signature("author_signature", "author")])

        digest = hashlib.sha256(contract.identity.module_id.encode() + artifact_digest).digest()
        state: LifecycleState = test_bypass_promote or initial_state
        mid = contract.identity.module_id
        with self._lock:
            self._modules[mid] = _Entry(
                contract=contract,
                state=state,
                artifact_digest=artifact_digest,
                module=module,
                contract_digest=digest,
            )
            self._audit.append(
                {
                    "event": "register",
                    "module_id": mid,
                    "at": datetime.now(UTC).isoformat(),
                    "signature_checked": self._trust_store is not None,
                }
            )
        self._trace.emit_lifecycle(
            LifecycleTraceEntry(module_id=mid, from_state="", to_state=state, event="register")
        )
        return RegisterResponse(module_id=mid, initial_state=state, validation_issues=issues)

    def deregister(self, module_id: str, drain: str, timeout_s: int, *, now: datetime | None = None) -> None:
        """Remove the module and let it drain. Its ``on_drain`` gets a deadline ``timeout_s`` after ``now``.

        ``now`` is injected for vectors and tests and defaults to the wall clock. Before K1b task 7 the deadline was
        ``now`` itself and ``timeout_s`` was ignored.
        """
        with self._lock:
            entry = self._modules.pop(module_id, None)
        if entry and entry.module is not None:
            start = now if now is not None else datetime.now(UTC)
            entry.module.on_drain(start + timedelta(seconds=timeout_s))
        self._trace.emit_lifecycle(
            LifecycleTraceEntry(
                module_id=module_id,
                from_state=entry.state if entry else "",
                to_state="RETIRED",
                event="deregister",
            )
        )

    def query(self, filter: CapabilityFilter) -> list[ModuleHandle]:
        out: list[ModuleHandle] = []
        with self._lock:
            for mid, e in self._modules.items():
                if filter.roles and e.contract.identity.role not in filter.roles:
                    continue
                if filter.min_reliability is not None and (
                    _TIER_RANK[e.contract.safety.reliability_tier]
                    > _TIER_RANK[filter.min_reliability]
                ):
                    continue
                if filter.min_lifecycle_state is not None:
                    def _rank(s: str) -> int:
                        if s == "DEVELOPMENT":
                            return _PROMOTE_ORDER.index("EXPLORATION")
                        if s in _EXTENDED_STATES:
                            return -1
                        return _PROMOTE_ORDER.index(s)
                    if _rank(e.state) < _rank(filter.min_lifecycle_state):
                        continue
                hw = getattr(e.contract.metabolic, "requires_special_hardware", None)
                hw_s = hw.value if hw is not None and hasattr(hw, "value") else (str(hw) if hw else "NONE")
                out.append(
                    ModuleHandle(
                        module_id=mid,
                        version=e.contract.identity.version,
                        role=e.contract.identity.role,
                        tier=e.contract.safety.reliability_tier,
                        state=e.state,
                        contract_digest=e.contract_digest,
                        hardware_requirement=hw_s or "NONE",
                    )
                )
        return out

    def get_contract(self, module_id: str) -> SubstrateContract:
        with self._lock:
            return self._modules[module_id].contract

    def health(self, module_id: str) -> HealthReport:
        with self._lock:
            entry = self._modules[module_id]
        if entry.module is not None:
            return entry.module.health()
        return HealthReport(module_id=module_id, status="HEALTHY", score=1.0)

    def get_module(self, module_id: str) -> Any:
        with self._lock:
            e = self._modules.get(module_id)
            return e.module if e else None

    def promote(
        self,
        module_id: str,
        from_state: LifecycleState,
        to_state: LifecycleState,
        shadow_records: list[ShadowValidationRecord],
        approver_signature: bytes,
        *,
        test_bypass_validation: bool = False,
        calibration: CalibrationRecord | None = None,
        measured: MeasuredMetabolics | None = None,
    ) -> PromoteResponse:
        with self._lock:
            entry = self._modules[module_id]
            if self._trust_store is not None and not verify_any(
                self._trust_store.approvers,
                approver_signature,
                promotion_payload(module_id, from_state, to_state, shadow_records),
            ):
                self._note_rejected("approver", module_id)
                return PromoteResponse(
                    accepted=False,
                    validation_issues=[_bad_signature("approver_signature", "approver")],
                )
            if entry.state != from_state and not test_bypass_validation:
                return PromoteResponse(
                    accepted=False,
                    validation_issues=[
                        ValidationIssue(
                            Severity.ERROR,
                            "lifecycle_mismatch",
                            "from_state",
                            f"actual={entry.state} expected={from_state}",
                        )
                    ],
                )
            fi = _PROMOTE_ORDER.index(from_state)
            ti = _PROMOTE_ORDER.index(to_state)
            if ti != fi + 1 and not test_bypass_validation:
                return PromoteResponse(
                    accepted=False,
                    validation_issues=[
                        ValidationIssue(
                            Severity.ERROR,
                            "invalid_promotion",
                            "to_state",
                            f"cannot promote {from_state} -> {to_state}",
                        )
                    ],
                )
            if to_state in GATED_STATES:
                gate_issues = shadow_gate(shadow_records, self._shadow_threshold)
                if gate_issues:
                    return PromoteResponse(accepted=False, validation_issues=gate_issues)
                tier = entry.contract.safety.reliability_tier
                if calibration is not None or (self._require_calibration and tier in CALIBRATED_TIERS):
                    if calibration is None:
                        return PromoteResponse(
                            accepted=False,
                            validation_issues=[
                                ValidationIssue(
                                    Severity.ERROR,
                                    "calibration_evidence_missing",
                                    "calibration",
                                    f"tier {tier.value} claims calibration and no record was given",
                                )
                            ],
                        )
                    cal_issues = calibration_gate(calibration, self._calibration_threshold)
                    if cal_issues:
                        return PromoteResponse(accepted=False, validation_issues=cal_issues)
                if measured is not None or self._require_measurement:
                    if measured is None:
                        return PromoteResponse(
                            accepted=False,
                            validation_issues=[
                                ValidationIssue(
                                    Severity.ERROR,
                                    "measurement_missing",
                                    "measured",
                                    "a measured metabolic record is required",
                                )
                            ],
                        )
                    met_issues = metabolic_gate(entry.contract.metabolic, measured, self._metabolic_tolerance)
                    if met_issues:
                        return PromoteResponse(accepted=False, validation_issues=met_issues)
            entry.state = to_state
        self._trace.emit_lifecycle(
            LifecycleTraceEntry(module_id=module_id, from_state=from_state, to_state=to_state, event="promote")
        )
        return PromoteResponse(accepted=True)

    def hot_swap(
        self, module_id: str, new_version: str, strategy: str, drain_timeout_s: float
    ) -> HotSwapResponse:
        with self._lock:
            entry = self._modules.get(module_id)
            if entry is None:
                return HotSwapResponse(
                    accepted=False,
                    validation_issues=[
                        ValidationIssue(Severity.ERROR, "not_found", "module_id", "unknown module")
                    ],
                )
            if not entry.contract.lifecycle.hot_swap_supported:
                return HotSwapResponse(
                    accepted=False,
                    validation_issues=[
                        ValidationIssue(
                            Severity.ERROR, "hot_swap_unsupported", "lifecycle", "module disallows hot-swap"
                        )
                    ],
                )
        return HotSwapResponse(accepted=True)

    def list_module_ids(self) -> list[str]:
        with self._lock:
            return list(self._modules.keys())
