"""TraceEmitter — A3.1 + SDK-6 (OQ-5): auto-populate policy_id/digest/level.

v0.2 hooks (`emit_immune` / `emit_hormone` / `emit_autonomic`) are documented
stubs: they require `attach_v02_sink()` or raise NotImplementedError. No full
HormoneBus / Immune / Autonomic runtime in v0.1 (E.8).
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
    on_drain_outcome: str | None = None  # started|completed|abandoned|killed
    on_drain_synthetic: bool = False
    emitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ImmuneTraceEntry:
    """Artifact H — immune decisions as FULL-salience control-affecting bindings."""
    decision: str
    antigen_score: float = 0.0
    classification: str = ""  # PAMP | Danger | Safe
    source_module_id: str = ""
    binding_key: str = "immune_decision"
    policy_id: str | None = None
    policy_digest: bytes | None = None
    level: str | None = None
    emitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class HormoneTraceEntry:
    """Artifact G — hormone reading as consumer saw it (Axiom 6 staleness)."""
    hormone_state_digest: str = ""
    cortisol: float = 0.0
    dopamine: float = 0.0
    oxytocin: float = 0.0
    melatonin: float = 0.0
    staleness_ms: float = 0.0
    source: str = "hormone_bus_mirror"
    policy_id: str | None = None
    policy_digest: bytes | None = None
    level: str | None = None
    emitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AutonomicTraceEntry:
    """Artifact I — autonomic modulation of router-exposed parameters."""
    from_mode: str = ""
    to_mode: str = ""
    preemption_class: str = ""
    cross_check_frequency: float | None = None
    exploration_budget: float | None = None
    trigger: str = ""
    policy_id: str | None = None
    policy_digest: bytes | None = None
    level: str | None = None
    emitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class V02TraceSink:
    """Optional sink for v0.2 biological trace kinds (stub until G–I runtime)."""

    def __init__(self) -> None:
        self.entries: list[Any] = []

    def record(self, entry: Any) -> None:
        self.entries.append(entry)


class TraceEmitter:
    """SDK-6: auto-populates policy_id, policy_digest, level from router state.

    If router_state is None (M1 stub / no router yet), emit_* still records
    entries with null policy fields and does NOT raise TraceUnavailable —
    documented stub behavior for pre-router milestones. Once a provider is
    attached, missing state raises TraceUnavailable.

    v0.2: emit_immune / emit_hormone / emit_autonomic require attach_v02_sink().
    """

    def __init__(self, router_state: RouterStateProvider | None = None) -> None:
        self._router = router_state
        self._entries: list[Any] = []
        self._strict = router_state is not None
        self._v02_sink: V02TraceSink | None = None

    def attach_router_state(self, provider: RouterStateProvider) -> None:
        self._router = provider
        self._strict = True

    def attach_v02_sink(self, sink: V02TraceSink) -> None:
        self._v02_sink = sink

    @property
    def entries(self) -> list[Any]:
        return list(self._entries)

    def _authoritative(self) -> tuple[str, bytes, str]:
        if self._router is None:
            if self._strict:
                raise TraceUnavailable("router state unavailable")
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
        pid, pdig, level = self._authoritative()
        for fname, value in (
            ("policy_id", pid or None),
            ("policy_digest", pdig or None),
            ("level", level or None),
        ):
            current = getattr(entry, fname, None)
            if self._strict and current is not None and current != value and current not in ("", b""):
                raise SDKInvariantViolation(
                    f"caller must not set {fname}; SDK auto-populates from router state"
                )
            object.__setattr__(
                entry,
                fname,
                value if self._strict else (current if current not in (None,) else value or None),
            )
        return entry

    def emit_routing(self, entry: RoutingTraceEntry) -> None:
        self._entries.append(self._stamp(entry))

    def emit_degradation(self, entry: DegradationTraceEntry) -> None:
        self._entries.append(self._stamp(entry))

    def emit_workspace(self, entry: WorkspaceTraceEntry) -> None:
        self._entries.append(self._stamp(entry))

    def emit_lifecycle(self, entry: LifecycleTraceEntry) -> None:
        self._entries.append(self._stamp(entry))

    def emit_immune(self, entry: ImmuneTraceEntry) -> None:
        if self._v02_sink is None:
            raise NotImplementedError(
                "v0.2 ImmuneLayer not enabled; attach_v02_sink() — see docs/v0.2/"
            )
        stamped = self._stamp(entry)
        self._v02_sink.record(stamped)
        self._entries.append(stamped)

    def emit_hormone(self, entry: HormoneTraceEntry) -> None:
        if self._v02_sink is None:
            raise NotImplementedError(
                "v0.2 HormoneBus not enabled; attach_v02_sink() — see docs/v0.2/"
            )
        stamped = self._stamp(entry)
        self._v02_sink.record(stamped)
        self._entries.append(stamped)

    def emit_autonomic(self, entry: AutonomicTraceEntry) -> None:
        if self._v02_sink is None:
            raise NotImplementedError(
                "v0.2 AutonomicController not enabled; attach_v02_sink() — see docs/v0.2/"
            )
        stamped = self._stamp(entry)
        self._v02_sink.record(stamped)
        self._entries.append(stamped)
