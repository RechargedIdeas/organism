"""TraceEmitter — A3.1 + SDK-6 (OQ-5): auto-populate policy_id/digest/level."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Protocol

from organism_sdk.errors import SDKInvariantViolation, TraceUnavailable


class RouterStateProvider(Protocol):
    def current_policy_id(self) -> str: ...
    def current_policy_digest(self) -> bytes: ...
    def current_level(self) -> str: ...


@dataclass
class RoutingTraceEntry:
    task_id: str
    form: str
    plan_type: str = "DispatchPlan"
    primary_module_id: str = ""
    rationale: dict[str, Any] = field(default_factory=dict)
    policy_id: str | None = None
    policy_digest: bytes | None = None
    level: str | None = None
    calibration_state: dict[str, Any] | None = None
    emitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DegradationTraceEntry:
    from_level: str
    to_level: str
    trigger_kind: str
    diagnosis_code: str = ""
    event_class: str = "transition"
    policy_id: str | None = None
    policy_digest: bytes | None = None
    level: str | None = None
    human_ack: bool | None = None
    emitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class WorkspaceTraceEntry:
    operation: str
    batch_id: str = ""
    accepted: int = 0
    rejections: list[dict[str, Any]] = field(default_factory=list)
    policy_id: str | None = None
    policy_digest: bytes | None = None
    level: str | None = None
    emitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LifecycleTraceEntry:
    module_id: str
    from_state: str
    to_state: str
    event: str
    policy_id: str | None = None
    policy_digest: bytes | None = None
    level: str | None = None
    emitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TraceEmitter:
    """SDK-6: auto-populates policy_id, policy_digest, level from router state.

    If router_state is None (M1 stub / no router yet), emit_* still records
    entries with null policy fields and does NOT raise TraceUnavailable —
    documented stub behavior for pre-router milestones. Once a provider is
    attached, missing state raises TraceUnavailable.
    """

    def __init__(self, router_state: RouterStateProvider | None = None) -> None:
        self._router = router_state
        self._entries: list[Any] = []
        self._strict = router_state is not None

    def attach_router_state(self, provider: RouterStateProvider) -> None:
        self._router = provider
        self._strict = True

    @property
    def entries(self) -> list[Any]:
        return list(self._entries)

    def _authoritative(self) -> tuple[str, bytes, str]:
        if self._router is None:
            if self._strict:
                raise TraceUnavailable("router state unavailable")
            # M1 stub: no router yet — leave fields unset
            return ("", b"", "")
        try:
            return (
                self._router.current_policy_id(),
                self._router.current_policy_digest(),
                self._router.current_level(),
            )
        except Exception as exc:  # noqa: BLE001
            raise TraceUnavailable(str(exc)) from exc

    def _stamp(self, entry: Any) -> Any:
        # Caller cannot override: if they set non-None while router is attached, error
        pid, pdig, level = self._authoritative()
        for fname, value in (("policy_id", pid or None), ("policy_digest", pdig or None), ("level", level or None)):
            current = getattr(entry, fname, None)
            if self._strict and current is not None and current != value and current not in ("", b""):
                raise SDKInvariantViolation(
                    f"caller must not set {fname}; SDK auto-populates from router state"
                )
            object.__setattr__(entry, fname, value if self._strict else (current if current not in (None,) else value or None))
        return entry

    def emit_routing(self, entry: RoutingTraceEntry) -> None:
        self._entries.append(self._stamp(entry))

    def emit_degradation(self, entry: DegradationTraceEntry) -> None:
        self._entries.append(self._stamp(entry))

    def emit_workspace(self, entry: WorkspaceTraceEntry) -> None:
        self._entries.append(self._stamp(entry))

    def emit_lifecycle(self, entry: LifecycleTraceEntry) -> None:
        self._entries.append(self._stamp(entry))
