"""Load and validate the pipeline's configuration: ``gates.yaml`` and ``pipeline.toml``."""

from __future__ import annotations

import os
import re
import shlex
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

TIER_RANK: dict[str, int] = {"precommit": 0, "fast": 1, "full": 2, "nightly": 3}
BUILTINS = frozenset(
    {"proto", "hygiene_staged", "hygiene_tree", "ruff_ratchet", "mypy_ratchet", "rustfmt_ratchet"}
)
KNOWN_TOOLS = frozenset({"python", "cargo", "protoc", "rustfmt", "clippy", "git"})
GATE_KEYS = frozenset(
    {
        "id",
        "tier",
        "command",
        "builtin",
        "env",
        "blocking",
        "exclusive",
        "cacheable",
        "retries",
        "timeout_s",
        "requires",
        "inputs",
        "status",
        "note",
    }
)
_GATE_ID = re.compile(r"^[a-z][a-z0-9_]*(?::[a-z0-9_]+)*$")
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


class ConfigError(ValueError):
    """A configuration file is malformed. The message names the file and the problem."""


@dataclass(frozen=True)
class Gate:
    """One pipeline step. Either ``command`` (a shell-free argv line) or ``builtin`` is set."""

    id: str
    tier: str
    command: str | None
    builtin: str | None
    env: dict[str, str]
    blocking: bool
    exclusive: bool
    cacheable: bool
    retries: int
    timeout_s: float | None
    requires: tuple[str, ...]
    inputs: tuple[str, ...]

    @property
    def rank(self) -> int:
        return TIER_RANK[self.tier]


@dataclass(frozen=True)
class Command:
    """A parsed command: leading ``NAME=value`` tokens become ``env``; the rest is ``argv``."""

    env: dict[str, str]
    argv: tuple[str, ...]


@dataclass(frozen=True)
class Preflight:
    min_python: tuple[int, int]
    modules: tuple[str, ...]
    min_free_gib: float
    collect_timeout_s: float
    collect_marker: str


@dataclass(frozen=True)
class Hygiene:
    max_file_mib: float
    forbidden: tuple[str, ...]


@dataclass(frozen=True)
class Lint:
    ruff_paths: tuple[str, ...]
    mypy_paths: tuple[str, ...]


@dataclass(frozen=True)
class Proto:
    source: str
    output: str


@dataclass(frozen=True)
class Pipeline:
    default_timeout_s: float
    jobs: int
    inputs: tuple[str, ...]
    env: dict[str, str]
    preflight: Preflight
    hygiene: Hygiene
    lint: Lint
    proto: Proto


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read ({exc.strerror})") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read ({exc.strerror})") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: invalid TOML: {exc}") from exc


def _section(data: Mapping[str, Any], name: str, source: str) -> Mapping[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: [{name}] must be a table")
    return value


def _str_list(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ConfigError(f"{where} must be a list of non-empty strings")
    return tuple(value)


def _parse_gate(raw: object, source: str) -> Gate:
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: each gate must be a mapping")
    gid = raw.get("id")
    if not isinstance(gid, str) or not _GATE_ID.match(gid):
        raise ConfigError(f"{source}: invalid gate id {gid!r}")
    where = f"{source}: gate {gid!r}"
    unknown = sorted(set(raw) - GATE_KEYS)
    if unknown:
        raise ConfigError(f"{where} has unknown keys: {', '.join(unknown)}")

    tier = raw.get("tier", "fast")
    if tier not in TIER_RANK:
        raise ConfigError(f"{where}: tier must be one of {', '.join(TIER_RANK)}")

    command = raw.get("command")
    builtin = raw.get("builtin")
    if (command is None) == (builtin is None):
        raise ConfigError(f"{where} needs exactly one of 'command' or 'builtin'")
    if command is not None and (not isinstance(command, str) or not command.strip()):
        raise ConfigError(f"{where}: command must be a non-empty string")
    if builtin is not None and builtin not in BUILTINS:
        raise ConfigError(f"{where}: unknown builtin {builtin!r}")

    env_raw = raw.get("env", {})
    if not isinstance(env_raw, dict):
        raise ConfigError(f"{where}: env must be a mapping")
    env = {str(k): str(v) for k, v in env_raw.items()}

    for flag in ("blocking", "exclusive", "cacheable"):
        if flag in raw and not isinstance(raw[flag], bool):
            raise ConfigError(f"{where}: {flag} must be true or false")

    retries = raw.get("retries", 0)
    if not isinstance(retries, int) or isinstance(retries, bool) or not 0 <= retries <= 3:
        raise ConfigError(f"{where}: retries must be an integer from 0 to 3")

    timeout = raw.get("timeout_s")
    if timeout is not None and (
        isinstance(timeout, bool) or not isinstance(timeout, int | float) or timeout <= 0
    ):
        raise ConfigError(f"{where}: timeout_s must be a positive number")

    requires = _str_list(raw.get("requires", []), f"{where}: requires")
    bad = sorted(set(requires) - KNOWN_TOOLS)
    if bad:
        raise ConfigError(f"{where}: unknown requires {', '.join(bad)}")

    inputs = _str_list(raw.get("inputs", []), f"{where}: inputs")

    return Gate(
        id=gid,
        tier=tier,
        command=command,
        builtin=builtin,
        env=env,
        blocking=raw.get("blocking", True),
        exclusive=raw.get("exclusive", False),
        cacheable=raw.get("cacheable", True),
        retries=retries,
        timeout_s=float(timeout) if timeout is not None else None,
        requires=requires,
        inputs=inputs,
    )


def load_gates(path: Path) -> list[Gate]:
    """Parse the ``gates:`` list. Ids must be unique. Documentation-only sections are ignored."""
    raw_list = _load_yaml(path).get("gates")
    if not isinstance(raw_list, list) or not raw_list:
        raise ConfigError(f"{path}: expected a non-empty 'gates' list")
    gates: list[Gate] = []
    seen: set[str] = set()
    for item in raw_list:
        gate = _parse_gate(item, str(path))
        if gate.id in seen:
            raise ConfigError(f"{path}: duplicate gate id {gate.id!r}")
        seen.add(gate.id)
        gates.append(gate)
    return gates


def load_pipeline(path: Path) -> Pipeline:
    data = _load_toml(path)
    defaults = _section(data, "defaults", str(path))
    pre = _section(data, "preflight", str(path))
    hyg = _section(data, "hygiene", str(path))
    lint = _section(data, "lint", str(path))
    proto = _section(data, "proto", str(path))
    env = _section(data, "env", str(path))

    min_py = pre.get("min_python", [3, 11])
    if not isinstance(min_py, list) or len(min_py) != 2 or not all(isinstance(v, int) for v in min_py):
        raise ConfigError(f"{path}: [preflight] min_python must be [major, minor]")
    jobs = defaults.get("jobs", 2)
    if not isinstance(jobs, int) or jobs < 1:
        raise ConfigError(f"{path}: [defaults] jobs must be a positive integer")

    return Pipeline(
        default_timeout_s=float(defaults.get("timeout_s", 900)),
        jobs=jobs,
        inputs=_str_list(defaults.get("inputs", []), f"{path}: [defaults] inputs"),
        env={str(k): str(v) for k, v in env.items()},
        preflight=Preflight(
            min_python=(min_py[0], min_py[1]),
            modules=_str_list(pre.get("modules", []), f"{path}: [preflight] modules"),
            min_free_gib=float(pre.get("min_free_gib", 2.0)),
            collect_timeout_s=float(pre.get("collect_timeout_s", 300)),
            collect_marker=str(pre.get("collect_marker", "not slow")),
        ),
        hygiene=Hygiene(
            max_file_mib=float(hyg.get("max_file_mib", 5.0)),
            forbidden=_str_list(hyg.get("forbidden", []), f"{path}: [hygiene] forbidden"),
        ),
        lint=Lint(
            ruff_paths=_str_list(lint.get("ruff_paths", []), f"{path}: [lint] ruff_paths"),
            mypy_paths=_str_list(lint.get("mypy_paths", []), f"{path}: [lint] mypy_paths"),
        ),
        proto=Proto(
            source=str(proto.get("source", "proto/organism/v1")),
            output=str(proto.get("output", "sdk/python/organism_sdk/_proto")),
        ),
    )


def split_command(raw: str, placeholders: Mapping[str, str]) -> Command:
    """Split a gate command without a shell, then fill ``{name}`` placeholders per token.

    Splitting happens before substitution so Windows paths keep their backslashes.
    ``PYTHONPATH`` is normalised from ``:``-separated to the platform separator.
    """
    try:
        tokens = shlex.split(raw, posix=True)
    except ValueError as exc:
        raise ConfigError(f"cannot parse command {raw!r}: {exc}") from exc
    env: dict[str, str] = {}
    while tokens and _ENV_ASSIGN.match(tokens[0]):
        name, _, value = tokens.pop(0).partition("=")
        env[name] = fill(value, placeholders)
    if not tokens:
        raise ConfigError(f"command has no program: {raw!r}")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = os.pathsep.join(p for p in env["PYTHONPATH"].split(":") if p)
    return Command(env=env, argv=tuple(fill(t, placeholders) for t in tokens))


def fill(text: str, placeholders: Mapping[str, str]) -> str:
    for key, value in placeholders.items():
        text = text.replace("{" + key + "}", value)
    return text
