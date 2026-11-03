"""Built-in steps: protobuf generation, hygiene scans, and lint and format ratchets.

Built-ins run in-process or through the venv, so they need no shell. Each returns a
``StepOutput`` with a return code that follows the same convention as a subprocess:
0 passed, 1 failed, None did not finish (crash, timeout, missing tool).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from organism_ci import hygiene, ratchet
from organism_ci.config import Pipeline
from organism_ci.environment import Tools, build_env

BASELINE_DIR = Path("ci") / "baselines"


@dataclass(frozen=True)
class StepOutput:
    returncode: int | None
    text: str
    summary: str = ""


def _tail(text: str, lines: int = 12) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def _run(argv: list[str], root: Path, env: dict[str, str], timeout_s: float) -> tuple[int | None, str]:
    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout_s:g}s"
    except OSError as exc:
        return None, f"cannot start {argv[0]}: {exc}"
    return proc.returncode, proc.stdout + proc.stderr


def generate_proto(tools: Tools, pipeline: Pipeline) -> tuple[bool, str]:
    """Regenerate Python protobuf modules with grpc_tools, mirroring the Makefile's flags."""
    if tools.python is None:
        return False, "no venv interpreter"
    source = Path(pipeline.proto.source)
    if source.parts[-2:] != ("organism", "v1"):
        return False, f"proto source must end in organism/v1, got {source.as_posix()}"
    include = source.parents[1]
    proto_files = sorted((tools.root / source).glob("*.proto"))
    if not proto_files:
        return False, f"no .proto files in {source.as_posix()}"
    output = tools.root / pipeline.proto.output
    output.mkdir(parents=True, exist_ok=True)
    argv = [
        str(tools.python),
        "-m",
        "grpc_tools.protoc",
        "-I",
        include.as_posix(),
        f"--python_out={output.as_posix()}",
        f"--grpc_python_out={output.as_posix()}",
        f"--pyi_out={output.as_posix()}",
        *[p.relative_to(tools.root / include).as_posix() for p in proto_files],
    ]
    rc, text = _run(argv, tools.root, build_env(tools, pipeline.env, {}), timeout_s=300)
    if rc != 0:
        return False, _tail(text, 4) or f"exit {rc}"
    return True, f"{len(proto_files)} file(s)"


def _hygiene(tools: Tools, pipeline: Pipeline, paths: list[str]) -> StepOutput:
    findings = hygiene.scan(
        tools.root,
        paths,
        forbidden=pipeline.hygiene.forbidden,
        max_file_mib=pipeline.hygiene.max_file_mib,
    )
    if findings:
        return StepOutput(1, hygiene.render(findings), f"{len(findings)} finding(s)")
    return StepOutput(0, "", f"{len(paths)} path(s) clean")


def hygiene_staged(tools: Tools, pipeline: Pipeline) -> StepOutput:
    return _hygiene(tools, pipeline, hygiene.staged_files(tools))


def hygiene_tree(tools: Tools, pipeline: Pipeline) -> StepOutput:
    return _hygiene(tools, pipeline, hygiene.tree_files(tools))


def _ratchet_command(tool: str, tools: Tools, pipeline: Pipeline) -> list[str] | None:
    if tool == "ruff":
        return [str(tools.python), "-m", "ruff", "check", *pipeline.lint.ruff_paths, "--output-format", "concise"]
    if tool == "mypy":
        return [str(tools.python), "-m", "mypy", *pipeline.lint.mypy_paths]
    if tool == "rustfmt" and tools.cargo:
        return [tools.program("cargo"), "fmt", "--all", "--", "--check"]
    return None


def run_ratchet(
    tool: str,
    tools: Tools,
    pipeline: Pipeline,
    env: dict[str, str],
    *,
    timeout_s: float,
    update: bool = False,
) -> StepOutput:
    """Run a lint or format tool and compare its findings with ``ci/baselines/<tool>.json``."""
    argv = _ratchet_command(tool, tools, pipeline)
    if argv is None:
        return StepOutput(None, f"{tool} is not available")
    rc, text = _run(argv, tools.root, env, timeout_s)
    if rc is None or rc not in (0, 1):
        return StepOutput(None, f"{tool} exited {rc}\n{_tail(text)}")

    current = ratchet.PARSERS[tool](text, tools.root)
    if rc != 0 and not current:
        return StepOutput(None, f"{tool} failed without parseable findings\n{_tail(text)}")

    baseline_path = tools.root / BASELINE_DIR / f"{tool}.json"
    if update:
        ratchet.write_baseline(baseline_path, tool, current)
        return StepOutput(0, "", f"baseline written: {sum(current.values())} finding(s)")

    outcome = ratchet.judge(tool, text, root=tools.root, baseline_path=baseline_path)
    if outcome.error:
        return StepOutput(None, outcome.describe())
    body = outcome.describe()
    if not outcome.ok:
        body += "\n" + _tail(text, 40)
    return StepOutput(0 if outcome.ok else 1, body, f"{outcome.total} finding(s)")


def run_builtin(name: str, tools: Tools, pipeline: Pipeline, env: dict[str, str], timeout_s: float) -> StepOutput:
    if name == "proto":
        ok, message = generate_proto(tools, pipeline)
        return StepOutput(0 if ok else None, message, message)
    if name == "hygiene_staged":
        return hygiene_staged(tools, pipeline)
    if name == "hygiene_tree":
        return hygiene_tree(tools, pipeline)
    tool = {"ruff_ratchet": "ruff", "mypy_ratchet": "mypy", "rustfmt_ratchet": "rustfmt"}.get(name)
    if tool is None:
        return StepOutput(None, f"unknown builtin {name!r}")
    return run_ratchet(tool, tools, pipeline, env, timeout_s=timeout_s)
