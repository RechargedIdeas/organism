"""Run one tier from start to finish: lock, preflight, gates, report, and exit code."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from organism_ci import preflight, report, runs
from organism_ci.cache import ResultCache, TreeDigest
from organism_ci.config import TIER_RANK, ConfigError, Gate, Pipeline, load_gates, load_pipeline
from organism_ci.environment import Tools, capture, resolve_tools
from organism_ci.execute import SKIP, Context, Executor, GateResult

EXIT_OK = 0
EXIT_GATE_FAILED = 1
EXIT_PREFLIGHT_FAILED = 2
EXIT_INTERNAL = 3
EXIT_CONFIG = 4
EXIT_BUSY = 5
EXIT_INTERRUPTED = 130
CONFIG_DIR = Path("ci")


@dataclass(frozen=True)
class Options:
    tier: str = "fast"
    only: tuple[str, ...] = ()
    jobs: int | None = None
    no_cache: bool = False
    fail_fast: bool = False
    skip_preflight: bool = False
    allow_skips: bool = False
    timeout_scale: float = 1.0
    hook: str | None = None


def say(text: str = "") -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def select_gates(gates: list[Gate], tier: str, only: tuple[str, ...]) -> list[Gate]:
    """A gate runs in every tier at or above its own. ``--only`` picks by id from all gates."""
    if only:
        known = {g.id for g in gates}
        unknown = sorted(set(only) - known)
        if unknown:
            raise ConfigError(f"unknown gate id(s): {', '.join(unknown)}")
        return [g for g in gates if g.id in only]
    rank = TIER_RANK[tier]
    return [g for g in gates if g.rank <= rank]


def _git_state(tools: Tools) -> tuple[str, int]:
    git = tools.program("git")
    head = capture([git, "rev-parse", "--short", "HEAD"], tools.root) or "no-commits"
    dirty = capture([git, "status", "--porcelain"], tools.root) or ""
    return head, len(dirty.splitlines())


def _finish(
    *,
    root: Path,
    run: runs.RunDir,
    opts: Options,
    started: str,
    t0: float,
    state: tuple[str, int],
    checks: list[preflight.Check],
    gates: list[GateResult],
    status: str,
    exit_code: int,
) -> None:
    head, dirty = state
    doc = report.build(
        tier=opts.tier,
        hook=opts.hook,
        started=started,
        duration_s=time.monotonic() - t0,
        head=head,
        dirty_paths=dirty,
        checks=checks,
        gates=gates,
        run_dir=run.path.relative_to(root).as_posix(),
        status=status,
        exit_code=exit_code,
    )
    run.report.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    runs.publish_latest(root, run.report)
    say()
    say(report.render(doc))
    say(f"full report: {run.report.relative_to(root).as_posix()}")


def run_tier(root: Path, opts: Options) -> int:
    """Execute a tier under the run lock. Returns the process exit code."""
    t0 = time.monotonic()
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        pipeline = load_pipeline(root / CONFIG_DIR / "pipeline.toml")
        gates = select_gates(load_gates(root / CONFIG_DIR / "gates.yaml"), opts.tier, opts.only)
    except ConfigError as exc:
        say(f"config error: {exc}")
        return EXIT_CONFIG

    lock = runs.RunLock(root)
    try:
        lock.acquire()
    except runs.LockBusy as exc:
        say(f"busy: {exc}. Wait for it to finish, or delete ci/runs/.lock if it is stale.")
        return EXIT_BUSY
    try:
        return _run_locked(root, opts, pipeline, gates, started, t0)
    except KeyboardInterrupt:
        say("interrupted")
        return EXIT_INTERRUPTED
    finally:
        lock.release()


def _run_locked(
    root: Path,
    opts: Options,
    pipeline: Pipeline,
    gates: list[Gate],
    started: str,
    t0: float,
) -> int:
    tools = resolve_tools(root)
    run = runs.new_run(root, opts.tier)
    state = _git_state(tools)
    say(f"Organism local pipeline | tier={opts.tier} | {len(gates)} gate(s) | run {run.path.name}")

    if opts.skip_preflight:
        checks = [preflight.Check("preflight", preflight.WARN, "skipped by --skip-preflight")]
    else:
        checks = preflight.run_preflight(tools, pipeline, quick=opts.tier == "precommit")
    for check in checks:
        say(f"  {check.status:<4}  {check.name:<18} {check.detail}")
        if check.status != preflight.PASS and check.fix:
            say(f"          fix: {check.fix}")

    if preflight.failed(checks):
        _finish(root=root, run=run, opts=opts, started=started, t0=t0, state=state, checks=checks,
                gates=[], status="PREFLIGHT_FAILED", exit_code=EXIT_PREFLIGHT_FAILED)
        return EXIT_PREFLIGHT_FAILED

    ctx = Context(
        tools=tools,
        pipeline=pipeline,
        run=run,
        cache=ResultCache(root / "ci" / "cache"),
        tree=TreeDigest(tools),
        read_cache=not opts.no_cache,
        timeout_scale=opts.timeout_scale,
        fail_fast=opts.fail_fast,
    )
    total = len(gates)
    finished = 0

    def progress(result: GateResult) -> None:
        nonlocal finished
        finished += 1
        say(f"  [{finished:>3}/{total}] {result.status:<7} {result.id:<30} {result.duration_s:6.1f}s")

    results = Executor(ctx, on_done=progress).run(gates, opts.jobs or pipeline.jobs)

    blocking = [r for r in results if r.failing and not (opts.allow_skips and r.status == SKIP)]
    exit_code = EXIT_GATE_FAILED if blocking else EXIT_OK
    _finish(root=root, run=run, opts=opts, started=started, t0=t0, state=state, checks=checks,
            gates=results, status="FAILED" if blocking else "PASS", exit_code=exit_code)
    return exit_code
