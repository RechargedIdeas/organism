"""Sandbox policy — resource caps, network allowlist, escape denials."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SandboxPolicy:
    """Containment policy for Organism process jails.

    CPU Everywhere: no GPU fields. Bio may_actuate never enabled here.
    """

    # Wall-clock timeout for a child job (seconds)
    timeout_s: float = 30.0
    # Address-space / RSS soft cap (MB); None = no RLIMIT_AS
    max_rss_mb: int | None = 512
    # CPU time soft+hard (seconds); None = unset
    cpu_time_s: int | None = 30
    # Max open file descriptors
    max_fds: int | None = 64
    # Max child processes (RLIMIT_NPROC); None = unset
    max_nproc: int | None = 32
    # Network: empty allowlist = deny all outbound sockets (best-effort)
    network_allowlist: list[str] = field(default_factory=list)
    allow_network: bool = False
    # Attempt Linux user/mount/pid/net namespaces when available
    use_namespaces: bool = True
    # Deny shell / interpreter escape patterns in argv
    deny_shell_escape: bool = True
    # Working directory for the child (None = inherit, remapped if ns)
    workdir: str | None = None
    # Extra env cleared in child (security)
    scrub_env_prefixes: tuple[str, ...] = ("AWS_", "OPENAI_", "ORGANISM_LLM_API_KEY")
    # Label for audit
    label: str = "default"
    # Self-sandbox: Organism wrapping its own workers
    self_sandbox: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["scrub_env_prefixes"] = list(self.scrub_env_prefixes)
        return d

    @classmethod
    def from_env(cls, **overrides: Any) -> "SandboxPolicy":
        def _f(name: str, default: float) -> float:
            raw = os.environ.get(name)
            return float(raw) if raw not in (None, "") else default

        def _i(name: str, default: int | None) -> int | None:
            raw = os.environ.get(name)
            if raw in (None, ""):
                return default
            return int(raw)

        def _b(name: str, default: bool) -> bool:
            raw = os.environ.get(name)
            if raw in (None, ""):
                return default
            return raw.strip().lower() in ("1", "true", "yes", "on")

        base = cls(
            timeout_s=_f("ORGANISM_JAIL_TIMEOUT_S", 30.0),
            max_rss_mb=_i("ORGANISM_JAIL_MAX_RSS_MB", 512),
            cpu_time_s=_i("ORGANISM_JAIL_CPU_TIME_S", 30),
            max_fds=_i("ORGANISM_JAIL_MAX_FDS", 64),
            max_nproc=_i("ORGANISM_JAIL_MAX_NPROC", 32),
            allow_network=_b("ORGANISM_JAIL_ALLOW_NETWORK", False),
            use_namespaces=_b("ORGANISM_JAIL_NAMESPACES", True),
            deny_shell_escape=_b("ORGANISM_JAIL_DENY_SHELL", True),
        )
        for k, v in overrides.items():
            if hasattr(base, k):
                setattr(base, k, v)
        return base

    @classmethod
    def generative(cls) -> "SandboxPolicy":
        """Tight policy for generative code drafts."""
        return cls.from_env(
            timeout_s=float(os.environ.get("ORGANISM_SANDBOX_TIMEOUT_S", "2") or 2),
            max_rss_mb=int(os.environ.get("ORGANISM_SANDBOX_MAX_RSS_MB", "256") or 256),
            cpu_time_s=5,
            max_fds=32,
            max_nproc=8,
            allow_network=False,
            label="generative",
            self_sandbox=False,
        )

    @classmethod
    def self_containment(cls) -> "SandboxPolicy":
        """Policy for Organism wrapping its own worker pool / soak / federation children."""
        return cls.from_env(
            timeout_s=float(os.environ.get("ORGANISM_SELF_JAIL_TIMEOUT_S", "600") or 600),
            max_rss_mb=int(os.environ.get("ORGANISM_SELF_JAIL_MAX_RSS_MB", "2048") or 2048),
            cpu_time_s=int(os.environ.get("ORGANISM_SELF_JAIL_CPU_TIME_S", "600") or 600),
            max_fds=256,
            max_nproc=128,
            allow_network=False,
            label="self_containment",
            self_sandbox=True,
        )


# Patterns refused when deny_shell_escape is on (argv / shell strings)
SHELL_ESCAPE_PATTERNS: tuple[str, ...] = (
    "/bin/sh",
    "/bin/bash",
    "/bin/zsh",
    "/bin/dash",
    "cmd.exe",
    "powershell",
    "pwsh",
    "os.system",
    "subprocess",
    "pty.spawn",
)
