"""Content-addressed result cache. A gate that passed on identical inputs is not run again.

A gate's key covers its id, its resolved command and environment, the toolchain versions, and
the bytes of every input file (tracked or untracked-but-not-ignored). Only passing results are
stored, and only gates marked ``cacheable`` take part. Timing-sensitive gates are never cached.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from organism_ci.environment import Tools
from organism_ci.hygiene import tree_files

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_name(gate_id: str) -> str:
    return _SAFE.sub("__", gate_id) + ".json"


class ResultCache:
    """One JSON file per gate. Every read error is a miss, so a damaged cache cannot fail a run."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def get(self, gate_id: str, key: str) -> dict[str, object] | None:
        path = self.directory / _safe_name(gate_id)
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(entry, dict) and entry.get("key") == key and entry.get("status") == "PASS":
            return entry
        return None

    def put(self, gate_id: str, key: str, *, duration_s: float) -> None:
        entry = {
            "key": key,
            "status": "PASS",
            "duration_s": round(duration_s, 3),
            "recorded": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / _safe_name(gate_id)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            return  # a cache that cannot be written only costs time on the next run


class TreeDigest:
    """Hashes repo files once per run. Gates pick subsets by path prefix or exact path."""

    def __init__(self, tools: Tools) -> None:
        self._tools = tools
        self._files: list[str] | None = None
        self._file_hashes: dict[str, bytes] = {}

    def _listing(self) -> list[str]:
        if self._files is None:
            self._files = sorted(tree_files(self._tools))
        return self._files

    def _hash_of(self, rel: str) -> bytes:
        cached = self._file_hashes.get(rel)
        if cached is None:
            path = self._tools.root / rel
            try:
                cached = hashlib.blake2b(path.read_bytes(), digest_size=16).digest()
            except OSError:
                cached = b"missing"
            self._file_hashes[rel] = cached
        return cached

    def digest(self, inputs: Iterable[str]) -> str:
        roots = tuple(p.rstrip("/") for p in inputs)
        hasher = hashlib.blake2b(digest_size=20)
        for rel in self._listing():
            if any(rel == root or rel.startswith(root + "/") for root in roots):
                hasher.update(rel.encode("utf-8"))
                hasher.update(b"\0")
                hasher.update(self._hash_of(rel))
        return hasher.hexdigest()


def cache_key(
    *,
    gate_id: str,
    argv: Iterable[str],
    env: dict[str, str],
    tools: Tools,
    tree_digest: str,
) -> str:
    hasher = hashlib.blake2b(digest_size=20)
    parts = [gate_id, " ".join(argv), json.dumps(sorted(env.items())), tools.fingerprint(), tree_digest]
    for part in parts:
        hasher.update(part.encode("utf-8"))
        hasher.update(b"\0")
    return hasher.hexdigest()
