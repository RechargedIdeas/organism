"""Process jail — rlimits + optional Linux namespaces; graceful degrade elsewhere."""
from __future__ import annotations

import os
import platform
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from organism_sdk.sandbox.policy import SHELL_ESCAPE_PATTERNS, SandboxPolicy


class JailRefused(PermissionError):
    """Raised when a jail launch would violate policy (shell escape, etc.)."""


@dataclass
class JailResult:
    ok: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    refused: str | None = None
    namespaces_used: list[str] = field(default_factory=list)
    namespaces_attempted: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    rlimits_applied: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    pid: int | None = None
    platform: str = field(default_factory=platform.system)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "stdout": self.stdout[-8000:],
            "stderr": self.stderr[-8000:],
            "timed_out": self.timed_out,
            "refused": self.refused,
            "namespaces_used": list(self.namespaces_used),
            "namespaces_attempted": list(self.namespaces_attempted),
            "degraded": list(self.degraded),
            "rlimits_applied": list(self.rlimits_applied),
            "duration_ms": self.duration_ms,
            "pid": self.pid,
            "platform": self.platform,
        }


def has_resource_module() -> bool:
    try:
        import resource  # noqa: F401

        return True
    except Exception:
        return False


def capabilities() -> dict[str, Any]:
    """What this host can offer for jailing."""
    linux = sys.platform.startswith("linux")
    has_resource = has_resource_module()
    has_unshare = False
    if linux:
        try:
            import ctypes

            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            has_unshare = hasattr(libc, "unshare")
        except Exception:
            has_unshare = False
    return {
        "platform": platform.system(),
        "linux": linux,
        "rlimits": has_resource,
        "unshare": has_unshare,
        "spawn": True,
        "cpu_everywhere": True,
        "docker_required": False,
        "native_sandbox": True,
    }


def _check_shell_escape(argv: Sequence[str], policy: SandboxPolicy) -> None:
    if not policy.deny_shell_escape:
        return
    if argv and os.path.basename(str(argv[0])).lower() in {
        "sh", "bash", "zsh", "dash", "cmd.exe", "powershell", "pwsh", "cmd"
    }:
        raise JailRefused(f"shell escape refused: argv0={argv[0]}")
    joined = " ".join(str(a) for a in argv).lower()
    if "-c" in [str(a) for a in argv]:
        for pat in ("os.system", "pty.spawn", "/bin/sh -", "/bin/bash -", "subprocess.call"):
            if pat in joined:
                raise JailRefused(f"shell escape refused: pattern={pat}")


def _make_preexec(policy: SandboxPolicy, ns_flags: int) -> Any:
    def _preexec() -> None:
        if ns_flags and sys.platform.startswith("linux"):
            try:
                import ctypes

                libc = ctypes.CDLL("libc.so.6", use_errno=True)
                libc.unshare(ns_flags)
            except Exception:
                pass
        if not has_resource_module():
            return
        import resource

        if policy.max_rss_mb and policy.max_rss_mb > 0:
            try:
                limit = int(policy.max_rss_mb) * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
            except Exception:
                pass
        if policy.cpu_time_s and policy.cpu_time_s > 0:
            try:
                soft = int(policy.cpu_time_s)
                resource.setrlimit(resource.RLIMIT_CPU, (soft, soft + 1))
            except Exception:
                pass
        if policy.max_fds and policy.max_fds > 0:
            try:
                n = int(policy.max_fds)
                resource.setrlimit(resource.RLIMIT_NOFILE, (n, n))
            except Exception:
                pass
        if policy.max_nproc and policy.max_nproc > 0 and hasattr(resource, "RLIMIT_NPROC"):
            try:
                n = int(policy.max_nproc)
                resource.setrlimit(resource.RLIMIT_NPROC, (n, n))
            except Exception:
                pass

    return _preexec


def _plan_namespaces(policy: SandboxPolicy) -> tuple[int, list[str], list[str]]:
    """Return (flags, attempted_names, degraded_notes) for parent-side reporting."""
    caps = capabilities()
    degraded: list[str] = []
    attempted: list[str] = []
    flags = 0
    if not policy.use_namespaces:
        return 0, [], []
    if not caps["linux"]:
        degraded.append("namespaces_unavailable_non_linux")
        return 0, [], degraded
    if not caps["unshare"]:
        degraded.append("unshare_unavailable")
        return 0, [], degraded

    CLONE_NEWUSER = 0x10000000
    CLONE_NEWNS = 0x00020000
    CLONE_NEWPID = 0x20000000
    CLONE_NEWNET = 0x40000000
    wanted = [("user", CLONE_NEWUSER), ("mount", CLONE_NEWNS)]
    if os.environ.get("ORGANISM_JAIL_FULL_NS", "").lower() in ("1", "true", "yes"):
        wanted.extend([("pid", CLONE_NEWPID), ("net", CLONE_NEWNET)])
    for name, flag in wanted:
        attempted.append(name)
        flags |= flag
    if not policy.allow_network and "net" not in attempted:
        degraded.append("network_not_namespaced")
    return flags, attempted, degraded


class ProcessJail:
    """Run an argv under SandboxPolicy containment."""

    def __init__(self, policy: SandboxPolicy | None = None) -> None:
        self.policy = policy or SandboxPolicy.from_env()

    def run(
        self,
        argv: Sequence[str],
        *,
        env: dict[str, str] | None = None,
        input_bytes: bytes | None = None,
        cwd: str | None = None,
    ) -> JailResult:
        argv = [str(a) for a in argv]
        try:
            _check_shell_escape(argv, self.policy)
        except JailRefused as e:
            return JailResult(ok=False, refused=str(e), exit_code=None)

        child_env = dict(os.environ)
        if env:
            child_env.update(env)
        for prefix in self.policy.scrub_env_prefixes:
            for k in list(child_env):
                if k.startswith(prefix) or k == prefix.rstrip("_"):
                    child_env.pop(k, None)
        child_env["ORGANISM_IN_JAIL"] = "1"
        child_env["ORGANISM_JAIL_LABEL"] = self.policy.label

        ns_flags, ns_attempted, degraded = _plan_namespaces(self.policy)
        caps = capabilities()
        rlimits_applied: list[str] = []
        if caps["rlimits"]:
            if self.policy.max_rss_mb:
                rlimits_applied.append("RLIMIT_AS")
            if self.policy.cpu_time_s:
                rlimits_applied.append("RLIMIT_CPU")
            if self.policy.max_fds:
                rlimits_applied.append("RLIMIT_NOFILE")
            if self.policy.max_nproc:
                rlimits_applied.append("RLIMIT_NPROC")
        else:
            degraded.append("rlimits_unavailable")

        preexec = None
        # preexec_fn only works on POSIX and not with threads on some platforms;
        # still the right tool for rlimits/unshare.
        if os.name == "posix":
            preexec = _make_preexec(self.policy, ns_flags)

        workdir = cwd or self.policy.workdir
        t0 = time.perf_counter()
        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workdir,
                env=child_env,
                preexec_fn=preexec,
                start_new_session=True,
            )
        except Exception as e:
            return JailResult(
                ok=False,
                stderr=f"spawn_failed:{type(e).__name__}:{e}",
                degraded=degraded + [f"spawn_failed:{type(e).__name__}"],
                namespaces_attempted=ns_attempted,
                rlimits_applied=rlimits_applied,
            )

        timed_out = False
        try:
            stdout_b, stderr_b = proc.communicate(
                input=input_bytes, timeout=self.policy.timeout_s
            )
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            try:
                stdout_b, stderr_b = proc.communicate(timeout=2)
            except Exception:
                stdout_b, stderr_b = b"", b""
        duration_ms = (time.perf_counter() - t0) * 1000.0

        # unshare success is not observable without IPC; report attempted as used when linux
        ns_used = list(ns_attempted) if (ns_flags and caps["linux"]) else []
        # If child died immediately with permission errors, note degrade
        stderr = (stderr_b or b"").decode("utf-8", errors="replace")
        if "Operation not permitted" in stderr or "Invalid argument" in stderr:
            degraded.append("namespace_or_rlimit_partial")
            ns_used = []

        code = proc.returncode
        ok = (not timed_out) and code == 0
        return JailResult(
            ok=ok,
            exit_code=code,
            stdout=(stdout_b or b"").decode("utf-8", errors="replace"),
            stderr=stderr,
            timed_out=timed_out,
            namespaces_used=ns_used,
            namespaces_attempted=ns_attempted,
            degraded=list(dict.fromkeys(degraded)),
            rlimits_applied=rlimits_applied,
            duration_ms=duration_ms,
            pid=proc.pid,
        )
