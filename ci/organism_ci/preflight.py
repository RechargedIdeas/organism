"""Preflight: confirm the machine and repo can run the pipeline before any gate starts.

Each check returns PASS, WARN, or FAIL. A FAIL stops the run before gates execute, so a broken
environment shows one clear message instead of dozens of confusing test failures. Preflight also
regenerates stale protobuf modules, which is an action, not only a report.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

from organism_ci.config import Pipeline
from organism_ci.environment import Tools, build_env, capture
from organism_ci.steps import generate_proto

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

_COLLECTED = re.compile(r"(\d+) tests? collected")
_MODULE_PROBE = (
    "import importlib.util, json, sys\n"
    "names = json.loads(sys.argv[1])\n"
    "print(json.dumps([n for n in names if importlib.util.find_spec(n) is None]))\n"
)


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""


def _runtime(_: Tools, pipeline: Pipeline) -> Check:
    want = pipeline.preflight.min_python
    have = sys.version_info[:2]
    if have < want:
        return Check("runner.python", FAIL, f"runner is {have[0]}.{have[1]}", f"use Python {want[0]}.{want[1]}+")
    return Check("runner.python", PASS, f"{have[0]}.{have[1]}")


def _venv(tools: Tools, pipeline: Pipeline) -> Check:
    if tools.python is None:
        return Check(
            "venv.python",
            FAIL,
            "no .venv interpreter found",
            'python -m venv .venv && .venv\\Scripts\\python -m pip install -e ".[dev,desktop]" pyyaml',
        )
    want = pipeline.preflight.min_python
    try:
        major, minor = (int(p) for p in tools.python_version.split(".")[:2])
    except ValueError:
        return Check("venv.python", FAIL, f"cannot read version from {tools.python}")
    if (major, minor) < want:
        return Check("venv.python", FAIL, f"venv is {major}.{minor}", "recreate .venv on a newer Python")
    return Check("venv.python", PASS, f"{tools.python_version} at {tools.python}")


def _modules(tools: Tools, pipeline: Pipeline) -> Check:
    if tools.python is None:
        return Check("venv.modules", FAIL, "skipped: no venv interpreter")
    names = list(pipeline.preflight.modules)
    out = capture([str(tools.python), "-c", _MODULE_PROBE, json.dumps(names)], tools.root)
    if out is None:
        return Check("venv.modules", FAIL, "module probe did not run", "check the venv is intact")
    missing = json.loads(out)
    if missing:
        return Check(
            "venv.modules",
            FAIL,
            f"missing: {', '.join(missing)}",
            'python -m pip install -e ".[dev,desktop]" pyyaml',
        )
    return Check("venv.modules", PASS, f"{len(names)} required modules importable")


def _git(tools: Tools, _: Pipeline) -> Check:
    if tools.git is None:
        return Check("git.repo", FAIL, "git not on PATH", "install Git for Windows")
    top = capture([tools.program("git"), "rev-parse", "--show-toplevel"], tools.root)
    if top is None:
        return Check("git.repo", FAIL, "not a git repository", "run from a clone of the repo")
    head = capture([tools.program("git"), "rev-parse", "--short", "HEAD"], tools.root) or "no commits"
    dirty = capture([tools.program("git"), "status", "--porcelain"], tools.root)
    changed = len(dirty.splitlines()) if dirty else 0
    return Check("git.repo", PASS, f"HEAD {head}, {changed} changed path(s)")


def _disk(tools: Tools, pipeline: Pipeline) -> Check:
    free_gib = shutil.disk_usage(tools.root).free / (1024**3)
    need = pipeline.preflight.min_free_gib
    if free_gib < need:
        return Check("disk.free", FAIL, f"{free_gib:.1f} GiB free, need {need:g}", "free disk space")
    return Check("disk.free", PASS, f"{free_gib:.1f} GiB free")


def _writable(tools: Tools, _: Pipeline) -> Check:
    target = tools.root / "ci" / "runs"
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return Check("fs.runs_dir", FAIL, f"cannot write {target}: {exc.strerror}")
    return Check("fs.runs_dir", PASS, str(target))


def _proto_stale(tools: Tools, pipeline: Pipeline) -> list[str]:
    """Protos whose generated module is missing or older. protoc mirrors the path under include/."""
    source = tools.root / pipeline.proto.source
    include = source.parents[1]
    output = tools.root / pipeline.proto.output
    stale: list[str] = []
    for proto in sorted(source.glob("*.proto")):
        generated = output / proto.relative_to(include).with_name(f"{proto.stem}_pb2.py")
        if not generated.is_file() or generated.stat().st_mtime < proto.stat().st_mtime:
            stale.append(proto.name)
    return stale


def _proto(tools: Tools, pipeline: Pipeline) -> Check:
    if tools.python is None:
        return Check("proto.generated", FAIL, "skipped: no venv interpreter")
    stale = _proto_stale(tools, pipeline)
    if not stale:
        return Check("proto.generated", PASS, "generated modules are current")
    ok, message = generate_proto(tools, pipeline)
    if not ok:
        return Check("proto.generated", FAIL, f"stale {', '.join(stale)}; regeneration failed: {message}")
    return Check("proto.generated", PASS, f"regenerated {len(stale)} proto file(s)")


def _protoc(tools: Tools, _: Pipeline) -> Check:
    if tools.protoc is None:
        return Check("tool.protoc", WARN, "not found; Rust gates will be skipped and fail", "set PROTOC or install protoc into .venv")
    return Check("tool.protoc", PASS, f"{tools.protoc_version} at {tools.protoc}")


def _cargo(tools: Tools, _: Pipeline) -> Check:
    if tools.cargo is None:
        return Check("tool.cargo", WARN, "not found; Rust gates will be skipped and fail", "install rustup")
    missing = sorted({"rustfmt", "clippy"} - set(tools.components))
    detail = f"{tools.cargo_version}"
    if missing:
        return Check("tool.cargo", WARN, f"{detail}; missing {', '.join(missing)}", "rustup component add " + " ".join(missing))
    return Check("tool.cargo", PASS, f"{detail}; rustfmt and clippy present")


def _collect(tools: Tools, pipeline: Pipeline) -> Check:
    if tools.python is None:
        return Check("tests.collect", FAIL, "skipped: no venv interpreter")
    argv = [str(tools.python), "-m", "pytest", "--collect-only", "-q", "-m", pipeline.preflight.collect_marker]
    env = build_env(tools, pipeline.env, {})
    try:
        proc = subprocess.run(
            argv,
            cwd=tools.root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=pipeline.preflight.collect_timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Check("tests.collect", FAIL, "collection timed out")
    text = proc.stdout + proc.stderr
    if proc.returncode != 0:
        tail = " | ".join(text.strip().splitlines()[-3:])
        return Check("tests.collect", FAIL, f"collection errors: {tail}", "fix the import error named above")
    match = _COLLECTED.search(text)
    count = match.group(1) if match else "?"
    return Check("tests.collect", PASS, f"{count} tests collected")


Probe = Callable[[Tools, Pipeline], Check]

_QUICK: tuple[Probe, ...] = (_runtime, _venv, _git)
_FULL: tuple[Probe, ...] = (
    _runtime,
    _venv,
    _modules,
    _git,
    _disk,
    _writable,
    _proto,
    _protoc,
    _cargo,
    _collect,
)


def run_preflight(tools: Tools, pipeline: Pipeline, *, quick: bool = False) -> list[Check]:
    """Run every probe even after a failure, so the operator sees all problems at once."""
    probes = _QUICK if quick else _FULL
    checks: list[Check] = []
    for probe in probes:
        try:
            checks.append(probe(tools, pipeline))
        except OSError as exc:  # a probe must never crash the runner
            checks.append(Check(probe.__name__.lstrip("_"), FAIL, f"probe error: {exc}"))
    return checks


def failed(checks: list[Check]) -> bool:
    return any(check.status == FAIL for check in checks)
