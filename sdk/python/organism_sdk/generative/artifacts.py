"""Versioned artifact store + provenance traces for generative outputs.

Concurrent-safe via RLock + atomic replace writes (v1.7.1).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


ArtifactKind = Literal["code", "asset", "skill", "manifest", "pack"]


@dataclass
class ProvenanceRecord:
    artifact_id: str
    kind: ArtifactKind
    version: int
    digest: str
    parent_digest: str | None
    backend: str
    stage: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "version": self.version,
            "digest": self.digest,
            "parent_digest": self.parent_digest,
            "backend": self.backend,
            "stage": self.stage,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


class ArtifactStore:
    """Filesystem-backed versioned store under ``root`` (CPU-only, no GPU).

    Concurrent-safe: process-local RLock around index + atomic file replace.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        for sub in ("code", "assets", "skills", "provenance", "packs"):
            (self.root / sub).mkdir(exist_ok=True)
        self._lock = threading.RLock()
        self._index: dict[str, list[ProvenanceRecord]] = {}
        self._load_index()

    def _load_index(self) -> None:
        idx = self.root / "provenance" / "index.json"
        if not idx.is_file():
            return
        try:
            raw = json.loads(idx.read_text(encoding="utf-8"))
            for aid, rows in raw.items():
                self._index[aid] = [ProvenanceRecord(**r) for r in rows]
        except Exception:
            self._index = {}

    def _save_index(self) -> None:
        idx = self.root / "provenance" / "index.json"
        payload = {aid: [r.as_dict() for r in rows] for aid, rows in self._index.items()}
        _atomic_write_text(idx, json.dumps(payload, indent=2, sort_keys=True))

    def put(
        self,
        *,
        kind: ArtifactKind,
        body: bytes | str,
        backend: str,
        stage: str,
        artifact_id: str | None = None,
        parent_digest: str | None = None,
        metadata: dict[str, Any] | None = None,
        suffix: str = ".bin",
    ) -> ProvenanceRecord:
        with self._lock:
            aid = artifact_id or f"{kind}_{uuid.uuid4().hex[:12]}"
            data = body.encode("utf-8") if isinstance(body, str) else body
            digest = _digest_bytes(data)
            versions = self._index.get(aid, [])
            version = (versions[-1].version + 1) if versions else 1
            sub = {
                "code": "code",
                "asset": "assets",
                "skill": "skills",
                "manifest": "assets",
                "pack": "packs",
            }[kind]
            path = self.root / sub / f"{aid}_v{version}{suffix}"
            _atomic_write_bytes(path, data)
            rec = ProvenanceRecord(
                artifact_id=aid,
                kind=kind,
                version=version,
                digest=digest,
                parent_digest=parent_digest,
                backend=backend,
                stage=stage,
                created_at=datetime.now(timezone.utc).isoformat(),
                metadata={**(metadata or {}), "path": str(path), "content_hash": digest},
            )
            self._index.setdefault(aid, []).append(rec)
            self._save_index()
            side = self.root / "provenance" / f"{aid}_v{version}.json"
            _atomic_write_text(side, json.dumps(rec.as_dict(), indent=2))
            return rec

    def latest(self, artifact_id: str) -> ProvenanceRecord | None:
        with self._lock:
            rows = self._index.get(artifact_id) or []
            return rows[-1] if rows else None

    def history(self, artifact_id: str) -> list[ProvenanceRecord]:
        with self._lock:
            return list(self._index.get(artifact_id) or [])

    def read_body(self, rec: ProvenanceRecord) -> bytes:
        path = Path(rec.metadata["path"])
        data = path.read_bytes()
        expected = rec.metadata.get("content_hash") or rec.digest
        if _digest_bytes(data) != expected:
            raise IntegrityError(
                f"content-hash mismatch for {rec.artifact_id} v{rec.version}: "
                f"expected={expected[:12]}…"
            )
        return data

    def verify(self, artifact_id: str) -> dict[str, Any]:
        """Verify content-hash integrity for all versions of an artifact."""
        with self._lock:
            rows = list(self._index.get(artifact_id) or [])
        ok = True
        details = []
        for rec in rows:
            path = Path(rec.metadata.get("path", ""))
            if not path.is_file():
                ok = False
                details.append({"version": rec.version, "ok": False, "error": "missing"})
                continue
            actual = _digest_bytes(path.read_bytes())
            match = actual == (rec.metadata.get("content_hash") or rec.digest)
            ok = ok and match
            details.append({"version": rec.version, "ok": match, "digest": actual[:16]})
        return {"artifact_id": artifact_id, "ok": ok, "versions": details}

    def list_ids(self, *, kind: ArtifactKind | None = None) -> list[str]:
        with self._lock:
            if kind is None:
                return sorted(self._index)
            return sorted(
                aid for aid, rows in self._index.items() if rows and rows[-1].kind == kind
            )


class IntegrityError(ValueError):
    """Raised when on-disk bytes do not match recorded content hash."""
