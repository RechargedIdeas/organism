"""Run directories, the single-run lock, the latest-run pointer, and pruning.

Everything the pipeline writes lives under ``ci/runs/`` (gitignored). Only one pipeline run may
hold the lock at a time, so a pre-push hook and a manual run cannot race on the same files.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from organism_ci.environment import capture

RUNS_SUBDIR = Path("ci") / "runs"
LOCK_NAME = ".lock"
LATEST_NAME = "latest.json"
_RUN_NAME = re.compile(r"^\d{8}T\d{6}Z-[a-z]+-\d+$")


class LockBusy(RuntimeError):
    """Another pipeline run holds the lock."""

    def __init__(self, holder: int) -> None:
        super().__init__(f"another pipeline run is active (pid {holder})")
        self.holder = holder


@dataclass(frozen=True)
class RunDir:
    path: Path

    @property
    def logs(self) -> Path:
        return self.path / "logs"

    @property
    def report(self) -> Path:
        return self.path / "report.json"


def runs_root(root: Path) -> Path:
    return root / RUNS_SUBDIR


def new_run(root: Path, tier: str) -> RunDir:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run = RunDir(runs_root(root) / f"{stamp}-{tier}-{os.getpid()}")
    run.logs.mkdir(parents=True, exist_ok=True)
    return run


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        out = capture(["tasklist", "/FI", f"PID eq {pid}", "/NH"], Path.cwd()) or ""
        return bool(re.search(rf"\b{pid}\b", out))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


class RunLock:
    """Exclusive lock file. A lock whose holder is gone is taken over automatically."""

    def __init__(self, root: Path) -> None:
        self.path = runs_root(root) / LOCK_NAME
        self._held = False

    def _holder(self) -> int | None:
        try:
            return int(self.path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                holder = self._holder()
                if holder is not None and _pid_alive(holder):
                    raise LockBusy(holder) from None
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            self._held = True
            return
        raise LockBusy(self._holder() or 0)

    def release(self) -> None:
        if self._held:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self._held = False

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()


def publish_latest(root: Path, report_path: Path) -> None:
    target = runs_root(root) / LATEST_NAME
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
    tmp.replace(target)


def latest_report(root: Path) -> dict[str, object] | None:
    path = runs_root(root) / LATEST_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def prune(root: Path, keep: int) -> list[Path]:
    """Delete all but the newest ``keep`` run directories. Only names this module creates qualify."""
    base = runs_root(root)
    if not base.is_dir():
        return []
    runs = sorted(p for p in base.iterdir() if p.is_dir() and _RUN_NAME.match(p.name))
    doomed = runs[: max(0, len(runs) - keep)]
    for path in doomed:
        shutil.rmtree(path, ignore_errors=True)
    return doomed
