"""Command-line interface: ``python ci/run.py [command] [options]``. ``run`` is the default."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from organism_ci import preflight, report, runs, steps
from organism_ci.config import TIER_RANK, ConfigError, load_gates, load_pipeline
from organism_ci.environment import build_env, resolve_tools
from organism_ci.orchestrator import (
    EXIT_CONFIG,
    EXIT_INTERNAL,
    EXIT_OK,
    Options,
    run_tier,
    say,
    select_gates,
)

COMMANDS = ("run", "doctor", "list", "baseline", "hooks", "status", "prune")
HOOKS_DIR = Path("ci") / "hooks"
RATCHET_TOOLS = ("ruff", "mypy", "rustfmt")
DEFAULT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    tiers = list(TIER_RANK)
    parser = argparse.ArgumentParser(prog="ci/run.py", description="Organism local CI pipeline.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a tier (the default command)")
    run.add_argument("--tier", choices=tiers, default="fast", help="precommit, fast, full, or nightly")
    run.add_argument("--only", action="append", default=[], metavar="GATE_ID", help="run one gate (repeatable)")
    run.add_argument("--jobs", type=int, help="parallel gates (default from pipeline.toml)")
    run.add_argument("--no-cache", action="store_true", help="ignore cached passes; still record new ones")
    run.add_argument("--fail-fast", action="store_true", help="stop scheduling after the first blocking failure")
    run.add_argument("--skip-preflight", action="store_true", help="do not run preflight (not recommended)")
    run.add_argument("--allow-skips", action="store_true", help="treat skipped blocking gates as passing")
    run.add_argument("--timeout-scale", type=float, default=1.0, help="multiply every gate timeout")
    run.add_argument("--hook", help=argparse.SUPPRESS)

    sub.add_parser("doctor", help="run preflight checks only")

    lst = sub.add_parser("list", help="show the gates a tier would run")
    lst.add_argument("--tier", choices=tiers, default="fast")
    lst.add_argument("--only", action="append", default=[], metavar="GATE_ID")

    base = sub.add_parser("baseline", help="record current lint/format findings as the new baseline")
    base.add_argument("tool", choices=RATCHET_TOOLS)

    hooks = sub.add_parser("hooks", help="install, remove, or show the git hooks")
    hooks.add_argument("action", choices=("install", "uninstall", "status"))

    sub.add_parser("status", help="show the latest run")

    prune = sub.add_parser("prune", help="delete old run directories")
    prune.add_argument("--keep", type=int, default=20)
    return parser


def _cmd_run(args: argparse.Namespace, root: Path) -> int:
    opts = Options(
        tier=args.tier,
        only=tuple(args.only),
        jobs=args.jobs,
        no_cache=args.no_cache,
        fail_fast=args.fail_fast,
        skip_preflight=args.skip_preflight,
        allow_skips=args.allow_skips,
        timeout_scale=args.timeout_scale,
        hook=args.hook,
    )
    return run_tier(root, opts)


def _cmd_doctor(root: Path) -> int:
    pipeline = load_pipeline(root / "ci" / "pipeline.toml")
    checks = preflight.run_preflight(resolve_tools(root), pipeline)
    for check in checks:
        say(f"  {check.status:<4}  {check.name:<18} {check.detail}")
        if check.status != preflight.PASS and check.fix:
            say(f"          fix: {check.fix}")
    return 2 if preflight.failed(checks) else EXIT_OK


def _cmd_list(args: argparse.Namespace, root: Path) -> int:
    gates = select_gates(load_gates(root / "ci" / "gates.yaml"), args.tier, tuple(args.only))
    say(f"{'GATE':<30} {'TIER':<9} {'BLOCK':<6} {'EXCL':<5} {'CACHE':<6} {'TIMEOUT':>8}  RUNS")
    for gate in gates:
        target = f"builtin:{gate.builtin}" if gate.builtin else (gate.command or "")
        timeout = f"{gate.timeout_s:g}s" if gate.timeout_s else "default"
        say(
            f"{gate.id:<30} {gate.tier:<9} {gate.blocking!s:<6} {gate.exclusive!s:<5} "
            f"{gate.cacheable!s:<6} {timeout:>8}  {target}"
        )
    say(f"{len(gates)} gate(s) for tier {args.tier}")
    return EXIT_OK


def _cmd_baseline(args: argparse.Namespace, root: Path) -> int:
    pipeline = load_pipeline(root / "ci" / "pipeline.toml")
    tools = resolve_tools(root)
    env = build_env(tools, pipeline.env, {})
    output = steps.run_ratchet(args.tool, tools, pipeline, env, timeout_s=900, update=True)
    if output.returncode is None:
        say(f"cannot record baseline: {output.text}")
        return EXIT_INTERNAL
    say(f"{args.tool}: {output.summary}")
    say(f"wrote {(steps.BASELINE_DIR / (args.tool + '.json')).as_posix()}; review the diff before committing")
    return EXIT_OK


def _git(root: Path, *args: str) -> tuple[int, str]:
    git = shutil.which("git")
    if git is None:
        return 127, "git not found on PATH"
    proc = subprocess.run(
        [git, *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _cmd_hooks(args: argparse.Namespace, root: Path) -> int:
    if args.action == "install":
        hooks = root / HOOKS_DIR
        missing = [name for name in ("pre-commit", "pre-push") if not (hooks / name).is_file()]
        if missing:
            say(f"hook files missing from {HOOKS_DIR.as_posix()}: {', '.join(missing)}")
            return EXIT_CONFIG
        rc, out = _git(root, "config", "core.hooksPath", HOOKS_DIR.as_posix())
        if rc != 0:
            say(f"git config failed: {out}")
            return EXIT_INTERNAL
        if os.name != "nt":
            for name in ("pre-commit", "pre-push"):
                path = hooks / name
                path.chmod(path.stat().st_mode | 0o755)
        say(f"hooks installed: core.hooksPath = {HOOKS_DIR.as_posix()}")
        say("pre-commit runs the precommit tier; pre-push runs the fast tier")
        return EXIT_OK
    if args.action == "uninstall":
        rc, out = _git(root, "config", "--unset", "core.hooksPath")
        if rc not in (0, 5):  # 5 means the key was not set
            say(f"git config failed: {out}")
            return EXIT_INTERNAL
        say("hooks removed")
        return EXIT_OK
    rc, out = _git(root, "config", "--get", "core.hooksPath")
    say(f"core.hooksPath = {out}" if rc == 0 else "hooks are not installed")
    return EXIT_OK


def _cmd_status(root: Path) -> int:
    latest = runs.latest_report(root)
    if latest is None:
        say("no runs recorded yet; try: python ci/run.py run --tier fast")
        return EXIT_OK
    say(report.render(latest, verbose=True))
    return EXIT_OK


def _cmd_prune(args: argparse.Namespace, root: Path) -> int:
    removed = runs.prune(root, args.keep)
    say(f"removed {len(removed)} run(s); kept the newest {args.keep}")
    return EXIT_OK


def main(argv: list[str] | None = None, root: Path = DEFAULT_ROOT) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw or (raw[0] not in COMMANDS and raw[0] not in ("-h", "--help")):
        raw = ["run", *raw]
    args = build_parser().parse_args(raw)
    try:
        if args.command == "run":
            return _cmd_run(args, root)
        if args.command == "doctor":
            return _cmd_doctor(root)
        if args.command == "list":
            return _cmd_list(args, root)
        if args.command == "baseline":
            return _cmd_baseline(args, root)
        if args.command == "hooks":
            return _cmd_hooks(args, root)
        if args.command == "status":
            return _cmd_status(root)
        return _cmd_prune(args, root)
    except ConfigError as exc:
        say(f"config error: {exc}")
        return EXIT_CONFIG
    except (OSError, ValueError) as exc:
        say(f"internal error: {exc}")
        return EXIT_INTERNAL
