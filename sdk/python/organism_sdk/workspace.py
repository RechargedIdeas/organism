"""WorkspaceClient — A3.1 surface; M1 in-memory implementation (no snapshot)."""
from __future__ import annotations

import hashlib
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from organism_sdk.errors import CapabilityScopeMissing
from organism_sdk.hypervector import Hypervector
from organism_sdk.trace import TraceEmitter, WorkspaceTraceEntry


@dataclass(frozen=True)
class BindingRecord:
    binding_id: UUID
    hypervector: Hypervector
    role: Hypervector
    filler: Hypervector
    tags: tuple[str, ...] = ()
    module_id: str = ""
    salience: float = 1.0
    fidelity: str = "FULL"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    checksum: bytes = b""
    # IMP-8 (v0.2): optional semantic payload for hormone_state / immune_decision / etc.
    payload: dict[str, Any] | None = None
    affects_control: bool = False

    def with_checksum(self) -> BindingRecord:
        h = hashlib.sha256()
        h.update(self.hypervector.to_bytes_be())
        h.update(self.role.to_bytes_be())
        h.update(self.filler.to_bytes_be())
        h.update(str(self.binding_id).encode())
        if self.payload is not None:
            import json as _json
            h.update(_json.dumps(self.payload, sort_keys=True, separators=(",", ":")).encode())
        h.update(b"1" if self.affects_control else b"0")
        h.update(self.fidelity.encode())
        return BindingRecord(
            binding_id=self.binding_id,
            hypervector=self.hypervector,
            role=self.role,
            filler=self.filler,
            tags=self.tags,
            module_id=self.module_id,
            salience=self.salience,
            fidelity=self.fidelity,
            created_at=self.created_at,
            checksum=h.digest(),
            payload=self.payload,
            affects_control=self.affects_control,
        )


@dataclass(frozen=True)
class BindingWriteResult:
    binding_id: UUID
    status: Literal["ACCEPTED", "REJECTED"]
    reason_code: str | None = None
    reason_params: dict[str, str] | None = None


class WorkspaceReader:
    """Capability-scoped read view handed to PerceptionInput."""

    def __init__(self, client: "WorkspaceClient", *, read_roles: tuple[str, ...], read_tags: tuple[str, ...]) -> None:
        self._client = client
        self._read_roles = set(read_roles)
        self._read_tags = set(read_tags)

    def read_by_tag(self, tags: list[str]) -> list[BindingRecord]:
        # IMP-21: requesting tags entirely outside capability scope is a violation
        if self._read_tags and self._read_tags != {"*"}:
            if tags and not (set(tags) & self._read_tags):
                raise CapabilityScopeMissing(
                    f"read tags {tags} not in capability scope {sorted(self._read_tags)}"
                )
        return self._client.read_by_tag(tags, _scoped_tags=self._read_tags)

    def read_by_binding_id(self, binding_id: UUID) -> BindingRecord | None:
        return self._client.read_by_binding_id(binding_id)

    def read_similar(self, hv: Hypervector, k: int = 10) -> list[tuple[BindingRecord, float]]:
        return self._client.read_similar(hv, k=k)


class WorkspaceClient:
    """In-memory workspace for M1/M2. Enforces SDK-1 capability check locally."""

    def __init__(
        self,
        *,
        write_roles: tuple[str, ...] = (),
        write_tags: tuple[str, ...] = (),
        read_roles: tuple[str, ...] = (),
        read_tags: tuple[str, ...] = (),
        trace: TraceEmitter | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._bindings: dict[UUID, BindingRecord] = {}
        self._write_roles = set(write_roles)
        self._write_tags = set(write_tags)
        self._read_roles = set(read_roles)
        self._read_tags = set(read_tags)
        self._trace = trace or TraceEmitter()
        self._seq = 0

    def reader(self) -> WorkspaceReader:
        return WorkspaceReader(self, read_roles=tuple(self._read_roles), read_tags=tuple(self._read_tags))

    def _check_write(self, binding: BindingRecord) -> None:
        # Role cue check is soft in M1: require write_roles non-empty permission if declared
        if self._write_tags and binding.tags:
            if not set(binding.tags) & self._write_tags and self._write_tags != {"*"}:
                raise CapabilityScopeMissing(f"write tags {binding.tags} not in {self._write_tags}")
        # IMP-21: immune_decision quarantine/control bindings cannot be forged
        immune_tags = [t for t in binding.tags if t == "immune_decision" or t.startswith("immune_decision/")]
        if immune_tags:
            if (
                binding.fidelity != "FULL"
                or not binding.affects_control
                or binding.module_id != "immune_layer"
                or binding.salience < 1.0
            ):
                raise CapabilityScopeMissing(
                    "immune_forgery: immune_decision requires module_id=immune_layer, "
                    "fidelity=FULL, affects_control=True, salience>=1.0"
                )

    def write(self, binding: BindingRecord) -> BindingWriteResult:
        return self.write_batch([binding])[0]

    def write_batch(self, bindings: list[BindingRecord]) -> list[BindingWriteResult]:
        results: list[BindingWriteResult] = []
        rejections: list[dict[str, Any]] = []
        accepted = 0
        batch_id = str(uuid.uuid4())
        with self._lock:
            for b in bindings:
                try:
                    self._check_write(b)
                except CapabilityScopeMissing as exc:
                    code = (
                        "immune_forgery_rejected"
                        if str(exc.detail).startswith("immune_forgery")
                        else "capability_scope_missing"
                    )
                    results.append(
                        BindingWriteResult(
                            binding_id=b.binding_id,
                            status="REJECTED",
                            reason_code=code,
                            reason_params={"detail": exc.detail},
                        )
                    )
                    rejections.append({"binding_id": str(b.binding_id), "reason_code": code})
                    continue
                stored = b.with_checksum() if not b.checksum else b
                # Bind exactness: role ⊕ filler should equal hypervector when both provided
                rebound = stored.role.bind(stored.filler)
                if rebound.to_bytes_be() != stored.hypervector.to_bytes_be():
                    # Auto-correct to role.bind(filler) for exactness invariant
                    stored = BindingRecord(
                        binding_id=stored.binding_id,
                        hypervector=rebound,
                        role=stored.role,
                        filler=stored.filler,
                        tags=stored.tags,
                        module_id=stored.module_id,
                        salience=stored.salience,
                        fidelity=stored.fidelity,
                        created_at=stored.created_at,
                        checksum=b"",
                        payload=stored.payload,
                        affects_control=stored.affects_control,
                    ).with_checksum()
                self._bindings[stored.binding_id] = stored
                self._seq += 1
                accepted += 1
                results.append(BindingWriteResult(binding_id=stored.binding_id, status="ACCEPTED"))
        self._trace.emit_workspace(
            WorkspaceTraceEntry(
                operation="write_batch",
                batch_id=batch_id,
                accepted=accepted,
                rejections=rejections,
            )
        )
        return results

    @property
    def binding_count(self) -> int:
        """Memory-growth proxy for soak / GC pressure (IMP-19)."""
        with self._lock:
            return len(self._bindings)

    def gc_ephemeral(
        self,
        *,
        max_bindings: int,
        protect_tags: tuple[str, ...] = ("hormone_state", "immune_decision"),
    ) -> int:
        """Unbind oldest non-affects_control bindings until at/under max_bindings.

        Never drops FULL/affects_control control bindings or protected tags.
        Returns number of bindings removed.
        """
        protect = set(protect_tags)
        removed = 0
        with self._lock:
            if len(self._bindings) <= max_bindings:
                return 0
            candidates = sorted(
                (
                    b
                    for b in self._bindings.values()
                    if not b.affects_control and not (set(b.tags) & protect)
                ),
                key=lambda b: b.created_at,
            )
            for b in candidates:
                if len(self._bindings) <= max_bindings:
                    break
                self._bindings.pop(b.binding_id, None)
                removed += 1
                self._seq += 1
        if removed:
            self._trace.emit_workspace(
                WorkspaceTraceEntry(
                    operation="gc_ephemeral",
                    batch_id=f"gc-{removed}",
                    accepted=removed,
                )
            )
        return removed

    def unbind(self, binding_id: UUID) -> BindingRecord | None:

        """Remove binding; return prior record. Exact inverse of write for that id."""
        with self._lock:
            prior = self._bindings.pop(binding_id, None)
        self._trace.emit_workspace(
            WorkspaceTraceEntry(operation="unbind", batch_id=str(binding_id), accepted=1 if prior else 0)
        )
        return prior

    def read_by_role(self, role_cue: Hypervector, k: int = 10) -> list[BindingRecord]:
        scored = []
        with self._lock:
            for b in self._bindings.values():
                scored.append((b.role.similarity(role_cue), b))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [b for _, b in scored[:k]]

    def read_by_tag(self, tags: list[str], _scoped_tags: set[str] | None = None) -> list[BindingRecord]:
        want = set(tags)
        scope = _scoped_tags if _scoped_tags is not None else self._read_tags
        out = []
        with self._lock:
            for b in self._bindings.values():
                if want & set(b.tags):
                    if scope and scope != {"*"} and not (set(b.tags) & scope):
                        continue
                    out.append(b)
        return out

    def read_by_binding_id(self, binding_id: UUID) -> BindingRecord | None:
        with self._lock:
            return self._bindings.get(binding_id)

    def read_similar(self, hv: Hypervector, k: int = 10) -> list[tuple[BindingRecord, float]]:
        scored = []
        with self._lock:
            for b in self._bindings.values():
                scored.append((b, b.hypervector.similarity(hv)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def read_by_provenance(
        self, module_id: str, time_range: tuple[datetime, datetime]
    ) -> list[BindingRecord]:
        start, end = time_range
        out = []
        with self._lock:
            for b in self._bindings.values():
                if b.module_id == module_id and start <= b.created_at <= end:
                    out.append(b)
        return out

    def bind_exact(
        self,
        role: Hypervector,
        filler: Hypervector,
        *,
        tags: tuple[str, ...] = (),
        module_id: str = "",
        payload: dict[str, Any] | None = None,
        affects_control: bool = False,
        fidelity: str = "FULL",
        salience: float = 1.0,
    ) -> BindingRecord:
        """Helper: create binding with hypervector = role.bind(filler)."""
        hv = role.bind(filler)
        rec = BindingRecord(
            binding_id=uuid.uuid4(),
            hypervector=hv,
            role=role,
            filler=filler,
            tags=tags,
            module_id=module_id,
            payload=payload,
            affects_control=affects_control,
            fidelity=fidelity,
            salience=salience,
        )
        result = self.write(rec)
        assert result.status == "ACCEPTED"
        got = self.read_by_binding_id(rec.binding_id)
        assert got is not None
        return got
