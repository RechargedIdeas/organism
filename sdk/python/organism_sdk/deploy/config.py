"""Deploy profile config load + validate (v1.4)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Minimal YAML subset without requiring PyYAML: we accept YAML-like via a
# tiny parser for our known schema, or JSON. Prefer json for robustness when
# PyYAML absent; also accept .yaml via stdlib-free key parsing for our files.


class DeployConfigError(ValueError):
    """Invalid deploy profile."""


@dataclass
class HealthConfig:
    host: str = "127.0.0.1"
    port: int = 8787
    path: str = "/health"
    status_path: str = "/status"


@dataclass
class StackConfig:
    register_deterministic: bool = True
    register_learned: bool = True
    workspace_write_tags: list[str] = field(default_factory=lambda: ["*"])
    workspace_read_tags: list[str] = field(default_factory=lambda: ["*"])
    router_level: str = "L0"
    # A trust store file of public keys (signing.load_trust_store). Set, the registry checks the
    # signatures on registrations and promotions; the built-in modules are exempt (GAP_ANALYSIS D5).
    trust_store: str | None = None


@dataclass
class RuntimeConfig:
    prefer_gpu: bool = False
    enable_bio_digital: bool = False
    enable_neuro_sim: bool = False
    hybrid_root: str | None = None


@dataclass
class ServeConfig:
    dry_run: bool = False
    bind_background: bool = True


@dataclass
class SandboxDeployConfig:
    """Native Organism sandbox knobs for a deploy profile (v1.10)."""

    self_sandbox: bool = True
    use_namespaces: bool = True
    timeout_s: float = 30.0
    max_rss_mb: int = 512


@dataclass
class WorkDeployConfig:
    """The work agent's deployment settings (v1.12). ``executor`` is the settings mapping of the
    Executor (see organism_sdk.work.executors.config), or None when no Executor is configured."""

    executor: dict[str, Any] | None = None
    # (source, row) pairs Eval listens to. None listens to every Trigger, which is what a config
    # without `work.listen` does. A present `work.listen` lists the pairs and nothing else.
    listen: tuple[tuple[str, str], ...] | None = None
    # The mode each Source's external writes run in: "off" (also what an unnamed Source gets),
    # "dry_run" (each reply is recorded, nothing is posted), or "on". OPEN_DECISIONS item 2.
    external_writes: dict[str, str] = field(default_factory=dict)


WRITE_SOURCES = frozenset({"github"})
WRITE_MODES = ("off", "dry_run", "on")


@dataclass
class DeployConfig:
    version: int = 1
    profile: str = "cpu_only"
    host_kind: str = "bare_metal"  # bare_metal|vm|container|unknown
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    stack: StackConfig = field(default_factory=StackConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    serve: ServeConfig = field(default_factory=ServeConfig)
    sandbox: SandboxDeployConfig = field(default_factory=SandboxDeployConfig)
    work: WorkDeployConfig = field(default_factory=WorkDeployConfig)
    source_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profile": self.profile,
            "host_kind": self.host_kind,
            "runtime": {
                "prefer_gpu": self.runtime.prefer_gpu,
                "enable_bio_digital": self.runtime.enable_bio_digital,
                "enable_neuro_sim": self.runtime.enable_neuro_sim,
                "hybrid_root": self.runtime.hybrid_root,
            },
            "stack": {
                "register_deterministic": self.stack.register_deterministic,
                "register_learned": self.stack.register_learned,
                "workspace_write_tags": list(self.stack.workspace_write_tags),
                "workspace_read_tags": list(self.stack.workspace_read_tags),
                "router_level": self.stack.router_level,
                "trust_store": self.stack.trust_store,
            },
            "health": {
                "host": self.health.host,
                "port": self.health.port,
                "path": self.health.path,
                "status_path": self.health.status_path,
            },
            "serve": {
                "dry_run": self.serve.dry_run,
                "bind_background": self.serve.bind_background,
            },
            "sandbox": {
                "self_sandbox": self.sandbox.self_sandbox,
                "use_namespaces": self.sandbox.use_namespaces,
                "timeout_s": self.sandbox.timeout_s,
                "max_rss_mb": self.sandbox.max_rss_mb,
            },
            "work": {
                "executor": self.work.executor,
                "listen": _listen_map(self.work.listen),
                "external_writes": dict(self.work.external_writes),
            },
            "source_path": self.source_path,
        }


def _coerce_bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off", ""}:
        return False
    return default


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the cpu_only.yaml schema without PyYAML.

    Supports nested maps via 2-space indent, lists as ["a","b"] or - items,
    scalars, null, bools, ints. Comments (#) stripped.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    pending_list_key: str | None = None
    pending_list_indent = -1
    pending_list: list[Any] | None = None

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        # list item
        if stripped.startswith("- "):
            item = stripped[2:].strip().strip('"').strip("'")
            if pending_list is None:
                raise DeployConfigError(f"list item without key: {stripped}")
            pending_list.append(item)
            continue

        if pending_list is not None and indent <= pending_list_indent:
            # close list into parent
            stack[-1][1][pending_list_key] = pending_list  # type: ignore[index]
            pending_list = None
            pending_list_key = None

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()

        if ":" not in stripped:
            raise DeployConfigError(f"expected key: {stripped}")
        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()

        if rest == "" or rest is None:
            # nested map or upcoming list
            child: dict[str, Any] = {}
            stack[-1][1][key] = child
            stack.append((indent, child))
            pending_list = None
            pending_list_key = None
            continue

        if rest.startswith("[") and rest.endswith("]"):
            inner = rest[1:-1].strip()
            if not inner:
                val: Any = []
            else:
                val = [p.strip().strip('"').strip("'") for p in inner.split(",")]
            stack[-1][1][key] = val
            continue

        # scalar
        if rest in {"null", "~", "Null", "NULL"}:
            val = None
        elif rest.lower() in {"true", "false"}:
            val = rest.lower() == "true"
        else:
            try:
                val = int(rest)
            except ValueError:
                try:
                    val = float(rest)
                except ValueError:
                    val = rest.strip('"').strip("'")
        stack[-1][1][key] = val

    if pending_list is not None and pending_list_key is not None:
        stack[-1][1][pending_list_key] = pending_list

    return root


def _from_mapping(data: dict[str, Any], *, source_path: str | None = None) -> DeployConfig:
    runtime_raw = data.get("runtime") or {}
    stack_raw = data.get("stack") or {}
    health_raw = data.get("health") or {}
    serve_raw = data.get("serve") or {}
    sandbox_raw = data.get("sandbox") or {}
    work_raw = data.get("work") or {}

    hybrid = runtime_raw.get("hybrid_root")
    if hybrid is not None:
        hybrid = str(hybrid)

    profile = str(data.get("profile", "cpu_only"))
    host_kind = str(
        data.get("host_kind")
        or {
            "bare_metal": "bare_metal",
            "vm": "vm",
            "container_generic": "container",
            "cpu_only": "bare_metal",
            "default": "bare_metal",
            "cpu_with_bio": "bare_metal",
            "research": "bare_metal",
        }.get(profile, "bare_metal")
    )

    cfg = DeployConfig(
        version=int(data.get("version", 1)),
        profile=profile,
        host_kind=host_kind,
        runtime=RuntimeConfig(
            prefer_gpu=_coerce_bool(runtime_raw.get("prefer_gpu"), False),
            enable_bio_digital=_coerce_bool(runtime_raw.get("enable_bio_digital"), False),
            enable_neuro_sim=_coerce_bool(runtime_raw.get("enable_neuro_sim"), False),
            hybrid_root=hybrid,
        ),
        stack=StackConfig(
            register_deterministic=_coerce_bool(stack_raw.get("register_deterministic"), True),
            register_learned=_coerce_bool(stack_raw.get("register_learned"), True),
            workspace_write_tags=list(stack_raw.get("workspace_write_tags") or ["*"]),
            workspace_read_tags=list(stack_raw.get("workspace_read_tags") or ["*"]),
            router_level=str(stack_raw.get("router_level", "L0")),
            trust_store=_optional_text(stack_raw.get("trust_store")),
        ),
        health=HealthConfig(
            host=str(health_raw.get("host", "127.0.0.1")),
            port=int(health_raw.get("port", 8787)),
            path=str(health_raw.get("path", "/health")),
            status_path=str(health_raw.get("status_path", "/status")),
        ),
        serve=ServeConfig(
            dry_run=_coerce_bool(serve_raw.get("dry_run"), False),
            bind_background=_coerce_bool(serve_raw.get("bind_background"), True),
        ),
        sandbox=SandboxDeployConfig(
            self_sandbox=_coerce_bool(sandbox_raw.get("self_sandbox"), True),
            use_namespaces=_coerce_bool(sandbox_raw.get("use_namespaces"), True),
            timeout_s=float(sandbox_raw.get("timeout_s", 30.0)),
            max_rss_mb=int(sandbox_raw.get("max_rss_mb", 512)),
        ),
        work=WorkDeployConfig(
            executor=_executor_section(work_raw.get("executor")),
            listen=_listen_section(work_raw["listen"]) if "listen" in work_raw else None,
            external_writes=_external_writes_section(work_raw.get("external_writes")),
        ),
        source_path=source_path,
    )
    return cfg


def _optional_text(value: Any) -> str | None:
    """A config value as text, or None when the key is absent or empty."""
    if value is None or str(value).strip() == "":
        return None
    return str(value)


def _executor_section(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise DeployConfigError("work.executor must be a mapping")
    return dict(value)


def _listen_map(pairs: tuple[tuple[str, str], ...] | None) -> dict[str, list[str]] | None:
    """The `work.listen` mapping for `pairs`, the form the config file uses. None stays None."""
    if pairs is None:
        return None
    rows: dict[str, list[str]] = {}
    for source, row in pairs:
        rows.setdefault(source, []).append(row)
    return rows


def _listen_section(value: Any) -> tuple[tuple[str, str], ...]:
    """`work.listen`: a mapping from each Source to the rows Eval listens to in it. A key that is
    present with no rows (a bare `listen:`) listens to none. The caller decides what absence means."""
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise DeployConfigError("work.listen must map each source to a list of rows")
    pairs: set[tuple[str, str]] = set()
    for source, rows in value.items():
        if not str(source).strip():
            raise DeployConfigError("work.listen has an empty source name")
        if not isinstance(rows, list) or not all(isinstance(r, str) and r.strip() for r in rows):
            raise DeployConfigError(f"work.listen.{source} must be a list of row names")
        pairs.update((str(source), row) for row in rows)
    return tuple(sorted(pairs))


def _external_writes_section(value: Any) -> dict[str, str]:
    """`work.external_writes`: the mode of each Source's writes. A Source not named stays off."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise DeployConfigError("work.external_writes must map each source to a mode")
    modes: dict[str, str] = {}
    for source, mode in value.items():
        if source not in WRITE_SOURCES:
            raise DeployConfigError(f"work.external_writes has an unknown source {source!r}")
        if mode not in WRITE_MODES:
            allowed = ", ".join(WRITE_MODES)
            raise DeployConfigError(
                f"work.external_writes.{source} must be one of {allowed}, not {mode!r}"
            )
        modes[str(source)] = str(mode)
    return modes


def default_cpu_only_config() -> DeployConfig:
    return DeployConfig(profile="cpu_only")


def load_deploy_config(path: str | Path | None = None) -> DeployConfig:
    """Load deploy YAML/JSON. None → built-in cpu_only defaults (+ env overlays)."""
    if path is None:
        env_path = os.environ.get("ORGANISM_CONFIG", "").strip()
        path = env_path or None

    if path is None:
        cfg = default_cpu_only_config()
    else:
        p = Path(path)
        if not p.is_file():
            raise DeployConfigError(f"config not found: {p}")
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() == ".json":
            import json

            data = json.loads(text)
        else:
            data = _parse_simple_yaml(text)
        if not isinstance(data, dict):
            raise DeployConfigError("config root must be a mapping")
        cfg = _from_mapping(data, source_path=str(p.resolve()))

    # Env overlays (CPU-only defaults stay unless explicitly enabled)
    if "ORGANISM_PREFER_GPU" in os.environ:
        cfg.runtime.prefer_gpu = _coerce_bool(os.environ.get("ORGANISM_PREFER_GPU"), False)
    if "ORGANISM_HEALTH_HOST" in os.environ:
        cfg.health.host = os.environ["ORGANISM_HEALTH_HOST"].strip() or cfg.health.host
    if "ORGANISM_HEALTH_PORT" in os.environ:
        cfg.health.port = int(os.environ["ORGANISM_HEALTH_PORT"])
    if os.environ.get("BIO_DIGITAL_HYBRID_ROOT", "").strip():
        cfg.runtime.hybrid_root = os.environ["BIO_DIGITAL_HYBRID_ROOT"].strip()
    if "ORGANISM_NEURO_SIM" in os.environ:
        cfg.runtime.enable_neuro_sim = _coerce_bool(os.environ.get("ORGANISM_NEURO_SIM"), False)

    return cfg


def validate_deploy_config(cfg: DeployConfig) -> list[str]:
    """Return list of issues (empty = ok). Never raises for soft warnings."""
    issues: list[str] = []
    if cfg.version != 1:
        issues.append(f"unsupported config version: {cfg.version}")
    if cfg.profile not in {
        "cpu_only",
        "default",
        "cpu_with_bio",
        "research",
        "bare_metal",
        "vm",
        "container_generic",
    }:
        issues.append(f"unknown profile: {cfg.profile}")
    if cfg.host_kind not in {"bare_metal", "vm", "container", "unknown"}:
        issues.append(f"unknown host_kind: {cfg.host_kind}")
    if not (1 <= cfg.health.port <= 65535):
        issues.append(f"invalid health.port: {cfg.health.port}")
    if not cfg.health.path.startswith("/"):
        issues.append("health.path must start with /")
    if not cfg.health.status_path.startswith("/"):
        issues.append("health.status_path must start with /")
    if cfg.stack.router_level not in {"L0", "L1", "L2", "L3", "L4"}:
        issues.append(f"invalid router_level: {cfg.stack.router_level}")
    if cfg.stack.trust_store is not None:
        from organism_sdk.signing import load_trust_store

        try:
            load_trust_store(Path(cfg.stack.trust_store))
        except (OSError, ValueError) as error:  # a JSON error is a ValueError
            issues.append(f"stack.trust_store: {error}")
    if cfg.runtime.prefer_gpu and cfg.profile == "cpu_only":
        # Soft warning — still valid; selection will fall back to CPU
        pass
    if cfg.runtime.hybrid_root:
        root = Path(cfg.runtime.hybrid_root)
        if not root.is_dir():
            issues.append(f"hybrid_root not a directory: {cfg.runtime.hybrid_root}")
    if cfg.work.executor is not None:
        from organism_sdk.work.executors.config import executor_from_settings

        try:
            executor_from_settings(cfg.work.executor)
        except ValueError as error:
            issues.append(f"work.executor: {error}")
    return issues
