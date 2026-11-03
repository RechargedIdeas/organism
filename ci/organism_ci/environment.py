"""Resolve the tools the pipeline needs, and build the environment gates run in."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from organism_ci.config import fill

PROBE_TIMEOUT_S = 60.0


@dataclass
class Tools:
    """What this machine offers. Versions feed the cache key so a toolchain change re-runs gates."""

    root: Path
    python: Path | None = None
    python_version: str = ""
    protoc: Path | None = None
    protoc_version: str = ""
    cargo: str | None = None
    cargo_version: str = ""
    git: str | None = None
    components: frozenset[str] = field(default_factory=frozenset)

    def has(self, name: str) -> bool:
        if name == "python":
            return self.python is not None
        if name == "protoc":
            return self.protoc is not None
        if name == "cargo":
            return self.cargo is not None
        if name == "git":
            return self.git is not None
        return name in self.components

    def placeholders(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if self.python is not None:
            values["python"] = str(self.python)
        if self.protoc is not None:
            values["protoc"] = str(self.protoc)
        return values

    def program(self, name: str) -> str:
        """Map a bare program name to the resolved path, so no PATH lookup happens at spawn."""
        if name == "cargo" and self.cargo:
            return self.cargo
        if name == "git" and self.git:
            return self.git
        return name

    def fingerprint(self) -> str:
        parts = (
            str(self.python),
            self.python_version,
            str(self.protoc),
            self.protoc_version,
            self.cargo_version,
            ",".join(sorted(self.components)),
        )
        return "|".join(parts)


def capture(argv: list[str], cwd: Path, timeout_s: float = PROBE_TIMEOUT_S) -> str | None:
    """Run a short probe and return its stdout, or None when it fails."""
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def venv_python(root: Path) -> Path | None:
    candidates = (
        [root / ".venv" / "Scripts" / "python.exe", root / ".venv" / "bin" / "python"]
        if sys.platform == "win32"
        else [root / ".venv" / "bin" / "python", root / ".venv" / "Scripts" / "python.exe"]
    )
    return next((path for path in candidates if path.is_file()), None)


def _resolve_protoc(root: Path) -> Path | None:
    explicit = os.environ.get("PROTOC")
    if explicit and Path(explicit).is_file():
        return Path(explicit)
    for name in ("protoc.exe", "protoc"):
        for sub in ("Scripts", "bin"):
            candidate = root / ".venv" / sub / name
            if candidate.is_file():
                return candidate
    found = shutil.which("protoc")
    return Path(found) if found else None


def resolve_tools(root: Path) -> Tools:
    tools = Tools(root=root)
    tools.git = shutil.which("git")

    tools.python = venv_python(root)
    if tools.python is not None:
        tools.python_version = capture(
            [str(tools.python), "-c", "import sys; print(sys.version.split()[0])"], root
        ) or ""

    tools.protoc = _resolve_protoc(root)
    if tools.protoc is not None:
        tools.protoc_version = capture([str(tools.protoc), "--version"], root) or ""

    tools.cargo = shutil.which("cargo")
    components: set[str] = set()
    if tools.cargo:
        tools.cargo_version = capture([tools.cargo, "--version"], root) or ""
        if capture([tools.cargo, "fmt", "--version"], root):
            components.add("rustfmt")
        if capture([tools.cargo, "clippy", "--version"], root):
            components.add("clippy")
    tools.components = frozenset(components)
    return tools


def build_env(tools: Tools, pipeline_env: dict[str, str], gate_env: dict[str, str]) -> dict[str, str]:
    """Inherit the parent environment, then apply pipeline defaults and gate overrides.

    Gate values take the same placeholders as commands, so {protoc} resolves to the real path.
    """
    env = dict(os.environ)
    env.update(pipeline_env)
    placeholders = tools.placeholders()
    env.update({name: fill(value, placeholders) for name, value in gate_env.items()})
    env.setdefault("PROTOC", str(tools.protoc) if tools.protoc else "")
    if not env["PROTOC"]:
        del env["PROTOC"]
    return env
