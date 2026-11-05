"""RegistryClient — A3.1; M1 in-process mock registry."""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from organism_sdk.contract import (
    ModuleRole,
    ReliabilityTier,
    Severity,
    SubstrateContract,
    ValidationIssue,
)
from organism_sdk.errors import RegistrationRejected
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

    ``builtin_ids`` are the module ids that are the deployment's own code, not generative output.
    With a trust store, a module whose id is listed registers without an author signature, and is
    audited as built in. Every other registration still needs one (OPEN_DECISIONS item D5, option b).
    The list is code, not configuration, so a config file cannot widen it.
    """

    def __init__(
        self,
        trace: TraceEmitter | None = None,
        *,
        trust_store: TrustStore | None = None,
        builtin_ids: frozenset[str] = frozenset(),
    ) -> None:
        self._lock = threading.RLock()
        self._modules: dict[str, _Entry] = {}
        self._trace = trace or TraceEmitter()
        self._audit: list[dict[str, Any]] = []
        self._trust_store = trust_store
        self._builtin_ids = builtin_ids

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

        mid = contract.identity.module_id
        # A built-in module is the deployment's own code, so it needs no author signature.
        built_in = mid in self._builtin_ids
        if (
            self._trust_store is not None
            and not built_in
            and not verify_any(
                self._trust_store.authors,
                author_signature,
                registration_payload(mid, contract.identity.version, artifact_digest),
            )
        ):
            self._note_rejected("author", mid)
            raise RegistrationRejected([_bad_signature("author_signature", "author")])

        digest = hashlib.sha256(mid.encode() + artifact_digest).digest()
        state: LifecycleState = test_bypass_promote or initial_state
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
                    "signature_checked": self._trust_store is not None and not built_in,
                    "built_in": built_in,
                }
            )
        self._trace.emit_lifecycle(
            LifecycleTraceEntry(module_id=mid, from_state="", to_state=state, event="register")
        )
        return RegisterResponse(module_id=mid, initial_state=state, validation_issues=issues)

    def deregister(self, module_id: str, drain: str, timeout_s: int) -> None:
        with self._lock:
            entry = self._modules.pop(module_id, None)
        if entry and entry.module is not None:
            entry.module.on_drain(datetime.now(UTC))
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
                hw_s = (
                    hw.value
                    if hw is not None and hasattr(hw, "value")
                    else (str(hw) if hw else "NONE")
                )
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
            report: HealthReport = entry.module.health()
            return report
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
            entry.state = to_state
        self._trace.emit_lifecycle(
            LifecycleTraceEntry(
                module_id=module_id, from_state=from_state, to_state=to_state, event="promote"
            )
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
                            Severity.ERROR,
                            "hot_swap_unsupported",
                            "lifecycle",
                            "module disallows hot-swap",
                        )
                    ],
                )
        return HotSwapResponse(accepted=True)

    def list_module_ids(self) -> list[str]:
        with self._lock:
            return list(self._modules.keys())
