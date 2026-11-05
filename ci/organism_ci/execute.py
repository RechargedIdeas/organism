"""Gate execution: scheduling, process supervision, retries, caching, and per-gate logs.

Gates run in parallel up to ``jobs``. Gates marked ``exclusive`` (timing budgets and full suites)
run alone after the parallel phase, so machine load cannot push a budget over its limit.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from organism_ci import steps
from organism_ci.cache import ResultCache, TreeDigest, cache_key, key_environment
from organism_ci.config import ConfigError, Gate, Pipeline, split_command
from organism_ci.environment import Tools, build_env
from organism_ci.procs import LIVE, POLL_S, kill_tree, wait_polling
from organism_ci.runs import RunDir

PASS = "PASS"
FAIL = "FAIL"
ERROR = "ERROR"
SKIP = "SKIP"
CACHED = "CACHED"
FLAKY = "FLAKY"
FAILING = frozenset({FAIL, ERROR, SKIP})

_COUNTS = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|deselected)\b")
_TAIL_BYTES = 256 * 1024
_BUILTIN_NEEDS: dict[str, frozenset[str]] = {
    "proto": frozenset({"python"}),
    "hygiene_staged": frozenset({"git"}),
    "hygiene_tree": frozenset({"git"}),
    "ruff_ratchet": frozenset({"python"}),
    "mypy_ratchet": frozenset({"python"}),
    "rustfmt_ratchet": frozenset({"cargo", "rustfmt"}),
}


@dataclass
class GateResult:
    id: str
    tier: str
    blocking: bool
    status: str = ""
    duration_s: float = 0.0
    attempts: int = 0
    returncode: int | None = None
    log: str = ""
    counts: dict[str, int] = field(default_factory=dict)
    note: str = ""

    @property
    def failing(self) -> bool:
        return self.blocking and self.status in FAILING

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "tier": self.tier,
            "blocking": self.blocking,
            "status": self.status,
            "duration_s": round(self.duration_s, 3),
            "attempts": self.attempts,
            "returncode": self.returncode,
            "log": self.log,
            "counts": self.counts,
            "note": self.note,
        }


@dataclass(frozen=True)
class Context:
    tools: Tools
    pipeline: Pipeline
    run: RunDir
    cache: ResultCache | None
    tree: TreeDigest
    read_cache: bool = True
    timeout_scale: float = 1.0
    fail_fast: bool = False


@dataclass
class _Attempt:
    returncode: int | None
    timed_out: bool
    text: str
    summary: str = ""


def parse_counts(text: str) -> dict[str, int]:
    """Read pytest's final summary line, e.g. ``4 failed, 447 passed, 4 skipped in 72s``."""
    for line in reversed(text.splitlines()):
        if " in " in line and _COUNTS.search(line):
            return {name: int(num) for num, name in _COUNTS.findall(line)}
    return {}


def _read_tail(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - _TAIL_BYTES))
            return handle.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _supervise(argv: list[str], env: dict[str, str], cwd: Path, timeout_s: float, log: Path) -> _Attempt:
    """Run a command with output going straight to its log file, and kill its tree on timeout."""
    group: dict[str, Any] = (
        {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    try:
        with log.open("ab") as handle:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                **group,
            )
    except OSError as exc:
        return _Attempt(None, False, f"cannot start {argv[0]}: {exc}")
    LIVE.add(proc)  # raises Interrupted, after killing the process, if the run is already aborting
    try:
        returncode = wait_polling(proc, timeout_s)
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        proc.wait()
        return _Attempt(None, True, _read_tail(log))
    except BaseException:  # interrupted: a gate must never outlive the runner
        kill_tree(proc)
        proc.wait()
        raise
    finally:
        LIVE.discard(proc)
    return _Attempt(returncode, False, _read_tail(log))


def _short(text: str, lines: int = 12) -> str:
    kept = [line for line in text.strip().splitlines() if line.strip()]
    return " | ".join(kept[-lines:])[-600:]


class Executor:
    """Runs gates and returns one ``GateResult`` per gate, in configuration order."""

    def __init__(self, ctx: Context, on_done: Callable[[GateResult], None] | None = None) -> None:
        self.ctx = ctx
        self._on_done = on_done or (lambda _result: None)
        self._emit_lock = threading.Lock()
        self._stop = threading.Event()

    def run(self, gates: Sequence[Gate], jobs: int) -> list[GateResult]:
        LIVE.reopen()
        results: dict[str, GateResult] = {}
        parallel = [g for g in gates if not g.exclusive]
        serial = [g for g in gates if g.exclusive]
        try:
            if parallel:
                with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
                    pending = {pool.submit(self._guarded, gate) for gate in parallel}
                    try:
                        while pending:
                            # Wake periodically: a blocking wait would hide Ctrl-C on Windows.
                            done, pending = wait(pending, timeout=POLL_S, return_when=FIRST_COMPLETED)
                            for future in done:
                                result = future.result()
                                results[result.id] = result
                    except KeyboardInterrupt:
                        self._abort()  # inside the with block: its exit waits for running gates
                        raise
            for gate in serial:
                results[gate.id] = self._guarded(gate)
        except KeyboardInterrupt:
            self._abort()
            raise
        return [results[gate.id] for gate in gates]

    def _abort(self) -> None:
        """Stop scheduling new gates and kill every gate process still running."""
        self._stop.set()
        LIVE.kill_all()

    def _guarded(self, gate: Gate) -> GateResult:
        result = GateResult(id=gate.id, tier=gate.tier, blocking=gate.blocking)
        if self._stop.is_set():
            result.status = SKIP
            result.note = "not run: fail-fast stopped the run"
            self._emit(result)
            return result
        started = time.monotonic()
        try:
            self._run_gate(gate, result)
        except (OSError, ConfigError, ValueError, RuntimeError) as exc:
            result.status = ERROR
            result.note = f"internal error: {exc}"
        result.duration_s = time.monotonic() - started
        if result.failing and self.ctx.fail_fast:
            self._stop.set()
        self._emit(result)
        return result

    def _emit(self, result: GateResult) -> None:
        with self._emit_lock:
            self._on_done(result)

    def _needs(self, gate: Gate) -> set[str]:
        needs = set(gate.requires)
        if gate.builtin is not None:
            return needs | set(_BUILTIN_NEEDS.get(gate.builtin, frozenset()))
        command = gate.command or ""
        if "{python}" in command:
            needs.add("python")
        if "{protoc}" in command or any("{protoc}" in v for v in gate.env.values()):
            needs.add("protoc")
        if "cargo" in command.split():
            needs.add("cargo")
        return needs

    def _run_gate(self, gate: Gate, result: GateResult) -> None:
        tools = self.ctx.tools
        missing = sorted(t for t in self._needs(gate) if not tools.has(t))
        if missing:
            result.status = SKIP
            result.note = f"missing: {', '.join(missing)}"
            return

        declared = {*self.ctx.pipeline.env, *gate.env}
        if gate.builtin is not None:
            argv: tuple[str, ...] = (gate.builtin,)
            env = build_env(tools, self.ctx.pipeline.env, gate.env)
        else:
            command = split_command(gate.command or "", tools.placeholders())
            argv = (tools.program(command.argv[0]), *command.argv[1:])
            env = build_env(tools, self.ctx.pipeline.env, {**gate.env, **command.env})
            declared.update(command.env)

        key = None
        if gate.cacheable and self.ctx.cache is not None:
            key = cache_key(
                gate_id=gate.id,
                argv=argv,
                env=key_environment(env, declared),
                tools=tools,
                tree_digest=self.ctx.tree.digest(gate.inputs or self.ctx.pipeline.inputs),
            )
            if self.ctx.read_cache and self.ctx.cache.get(gate.id, key) is not None:
                result.status = CACHED
                result.note = "unchanged since last pass"
                return

        timeout_s = (gate.timeout_s or self.ctx.pipeline.default_timeout_s) * self.ctx.timeout_scale
        log = self.ctx.run.logs / (re.sub(r"[^A-Za-z0-9_.-]", "__", gate.id) + ".log")
        result.log = log.relative_to(tools.root).as_posix()

        for attempt in range(1, gate.retries + 2):
            outcome = self._attempt(gate, gate.builtin, argv, env, timeout_s, attempt, log)
            result.attempts = attempt
            result.returncode = outcome.returncode
            result.counts = parse_counts(outcome.text)
            if outcome.returncode == 0:
                result.status = PASS if attempt == 1 else FLAKY
                result.note = "passed on retry" if attempt > 1 else outcome.summary
                break
            result.note = "timed out" if outcome.timed_out else _short(outcome.text)
        else:
            result.status = ERROR if outcome.timed_out or outcome.returncode is None else FAIL

        if result.status in (PASS, FLAKY) and key is not None and self.ctx.cache is not None:
            self.ctx.cache.put(gate.id, key, duration_s=result.duration_s)

    def _attempt(
        self,
        gate: Gate,
        builtin: str | None,
        argv: tuple[str, ...],
        env: dict[str, str],
        timeout_s: float,
        attempt: int,
        log: Path,
    ) -> _Attempt:
        with log.open("ab") as handle:
            handle.write(f"\n=== attempt {attempt}: {' '.join(argv)}\n".encode())
        if builtin is not None:
            output = steps.run_builtin(builtin, self.ctx.tools, self.ctx.pipeline, env, timeout_s)
            with log.open("ab") as handle:
                handle.write((output.text + "\n").encode("utf-8", "replace"))
            return _Attempt(output.returncode, False, output.text, output.summary)
        return _supervise(list(argv), env, self.ctx.tools.root, timeout_s, log)
