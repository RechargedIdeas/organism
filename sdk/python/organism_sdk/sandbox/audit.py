"""Sandbox audit log — optional TraceEmitter integration."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


class TraceLike(Protocol):
    def emit_sandbox(self, entry: Any) -> None: ...


@dataclass
class SandboxAuditEvent:
    action: str  # status|run|self_check|refuse|timeout|ok|error
    label: str = "default"
    ok: bool = True
    detail: str = ""
    policy: dict[str, Any] = field(default_factory=dict)
    pid: int | None = None
    exit_code: int | None = None
    namespaces_used: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    duration_ms: float | None = None
    emitted_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class SandboxAuditLog:
    """In-memory ring + optional TraceEmitter sink."""

    def __init__(self, *, capacity: int = 256, tracer: Any | None = None) -> None:
        self._capacity = max(16, capacity)
        self._events: list[SandboxAuditEvent] = []
        self._tracer = tracer

    def attach_tracer(self, tracer: Any) -> None:
        self._tracer = tracer

    def record(self, event: SandboxAuditEvent) -> SandboxAuditEvent:
        self._events.append(event)
        if len(self._events) > self._capacity:
            self._events = self._events[-self._capacity :]
        if self._tracer is not None:
            try:
                from organism_sdk.trace import SandboxTraceEntry

                self._tracer.emit_sandbox(
                    SandboxTraceEntry(
                        action=event.action,
                        label=event.label,
                        ok=event.ok,
                        detail=event.detail,
                        namespaces_used=list(event.namespaces_used),
                        degraded=list(event.degraded),
                    )
                )
            except Exception:
                pass
        return event

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return [e.as_dict() for e in self._events[-limit:]]

    def clear(self) -> None:
        self._events.clear()
