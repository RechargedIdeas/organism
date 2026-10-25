"""Versioned artifact store + provenance traces for generative outputs."""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


ArtifactKind = Literal["code", "asset", "skill", "manifest"]


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


class ArtifactStore:
    """Filesystem-backed versioned store under ``root`` (CPU-only, no GPU)."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "code").mkdir(exist_ok=True)
        (self.root / "assets").mkdir(exist_ok=True)
        (self.root / "skills").mkdir(exist_ok=True)
        (self.root / "provenance").mkdir(exist_ok=True)
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
        idx.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

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
            sub = {"code": "code", "asset": "assets", "skill": "skills", "manifest": "assets"}[kind]
            path = self.root / sub / f"{aid}_v{version}{suffix}"
            path.write_bytes(data)
            rec = ProvenanceRecord(
                artifact_id=aid,
                kind=kind,
                version=version,
                digest=digest,
                parent_digest=parent_digest,
                backend=backend,
                stage=stage,
                created_at=datetime.now(timezone.utc).isoformat(),
                metadata={**(metadata or {}), "path": str(path)},
            )
            self._index.setdefault(aid, []).append(rec)
            self._save_index()
            # also write provenance sidecar
            side = self.root / "provenance" / f"{aid}_v{version}.json"
            side.write_text(json.dumps(rec.as_dict(), indent=2), encoding="utf-8")
            return rec

    def latest(self, artifact_id: str) -> ProvenanceRecord | None:
        rows = self._index.get(artifact_id) or []
        return rows[-1] if rows else None

    def history(self, artifact_id: str) -> list[ProvenanceRecord]:
        return list(self._index.get(artifact_id) or [])

    def read_body(self, rec: ProvenanceRecord) -> bytes:
        path = Path(rec.metadata["path"])
        return path.read_bytes()

    def list_ids(self, *, kind: ArtifactKind | None = None) -> list[str]:
        if kind is None:
            return sorted(self._index)
        return sorted(aid for aid, rows in self._index.items() if rows and rows[-1].kind == kind)
