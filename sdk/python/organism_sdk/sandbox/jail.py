"""Process jail — rlimits + optional Linux namespaces; graceful degrade elsewhere."""

from __future__ import annotations

import contextlib
import logging
import os
import platform
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from organism_sdk.envstore import without_stored
from organism_sdk.sandbox.egress import Allow, EgressProxy
from organism_sdk.sandbox.policy import SandboxPolicy

logger = logging.getLogger(__name__)


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
        logger.debug("has_resource_module failed", exc_info=True)
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
            logger.debug("capabilities failed", exc_info=True)
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
        "sh",
        "bash",
        "zsh",
        "dash",
        "cmd.exe",
        "powershell",
        "pwsh",
        "cmd",
    }:
        raise JailRefused(f"shell escape refused: argv0={argv[0]}")
    joined = " ".join(str(a) for a in argv).lower()
    if "-c" in [str(a) for a in argv]:
        for pat in ("os.system", "pty.spawn", "/bin/sh -", "/bin/bash -", "subprocess.call"):
            if pat in joined:
                raise JailRefused(f"shell escape refused: pattern={pat}")


SIOCGIFFLAGS = 0x8913
SIOCSIFFLAGS = 0x8914
IFF_UP = 0x1
IFREQ = "16sh14x"  # struct ifreq: the interface name, then the flags


def _bring_up_loopback() -> None:
    """Set loopback up in a new network namespace, where it starts down.

    This runs in the forked child before exec. Exec drops the capabilities that a namespace grants
    to a process that is not root inside it, so a bridge started after exec could not do this.
    """
    if sys.platform == "win32":
        raise OSError("loopback can only be brought up on Linux")
    import fcntl  # Linux only, so not at module level, where Windows would fail

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        flags = struct.unpack(IFREQ, fcntl.ioctl(sock, SIOCGIFFLAGS, struct.pack(IFREQ, b"lo", 0)))[
            1
        ]
        fcntl.ioctl(sock, SIOCSIFFLAGS, struct.pack(IFREQ, b"lo", flags | IFF_UP))
    finally:
        sock.close()


def _make_preexec(policy: SandboxPolicy, ns_flags: int) -> Any:
    # Runs in the forked child before exec. Logging there can deadlock on a lock another
    # thread held at fork time, so a limit that cannot be applied is skipped silently.
    # Enforcement is the exception: a child that could not get its own namespace must not run,
    # so the error is raised, and the spawn fails and is reported.
    def _preexec() -> None:
        if ns_flags and sys.platform.startswith("linux"):
            unshared = False
            try:
                import ctypes

                libc = ctypes.CDLL("libc.so.6", use_errno=True)
                unshared = libc.unshare(ns_flags) == 0
            except Exception:  # noqa: BLE001, S110
                pass
            if policy.enforce_network:
                if not unshared:
                    raise OSError("the network namespace could not be made")
                _bring_up_loopback()
        if not has_resource_module():
            return
        import resource

        if policy.max_rss_mb and policy.max_rss_mb > 0:
            try:
                limit = int(policy.max_rss_mb) * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
            except Exception:  # noqa: BLE001, S110
                pass
        if policy.cpu_time_s and policy.cpu_time_s > 0:
            try:
                soft = int(policy.cpu_time_s)
                resource.setrlimit(resource.RLIMIT_CPU, (soft, soft + 1))
            except Exception:  # noqa: BLE001, S110
                pass
        if policy.max_fds and policy.max_fds > 0:
            try:
                n = int(policy.max_fds)
                resource.setrlimit(resource.RLIMIT_NOFILE, (n, n))
            except Exception:  # noqa: BLE001, S110
                pass
        if policy.max_nproc and policy.max_nproc > 0 and hasattr(resource, "RLIMIT_NPROC"):
            try:
                n = int(policy.max_nproc)
                resource.setrlimit(resource.RLIMIT_NPROC, (n, n))
            except Exception:  # noqa: BLE001, S110
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
    full = os.environ.get("ORGANISM_JAIL_FULL_NS", "").lower() in ("1", "true", "yes")
    if full:
        wanted.append(("pid", CLONE_NEWPID))
    if full or policy.enforce_network:
        wanted.append(("net", CLONE_NEWNET))
    for name, flag in wanted:
        attempted.append(name)
        flags |= flag
    if not policy.allow_network and "net" not in attempted:
        degraded.append("network_not_namespaced")
    return flags, attempted, degraded


# What a child gets, with or without an allowlist, so programs find their tools and temp files.
ENV_BASE = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "USERPROFILE")


def allowlisted_env(
    names: Sequence[str],
    *,
    extra: dict[str, str] | None = None,
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """A child environment with the base variables and the named ones, and nothing else inherited.

    A named variable passes even when the store holds it: the allowlist is the decision to pass it.
    """
    keep = set(ENV_BASE) | set(names)
    child_env = {k: v for k, v in (os.environ if source is None else source).items() if k in keep}
    if extra:
        child_env.update(extra)
    return child_env


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    """Kill a child's process group, and reap the child, when the caller cannot take the child."""
    if sys.platform == "win32":  # mypy checks each platform's branch only on that platform
        proc.kill()
    else:
        with contextlib.suppress(OSError):
            os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


BRIDGE_PORT = 3128  # the in-child bridge's port, on the child's own loopback, so any free port
BRIDGE = Path(__file__).with_name("egress_bridge.py")


class ProcessJail:
    """Run an argv under SandboxPolicy containment.

    `proxy_allow` replaces the allowlist that the egress proxy enforces when the policy sets
    `enforce_network`. Tests use it to reach a loopback server. The work executor never passes it.
    """

    def __init__(
        self, policy: SandboxPolicy | None = None, *, proxy_allow: Allow | None = None
    ) -> None:
        self.policy = policy or SandboxPolicy.from_env()
        self.proxy_allow = proxy_allow

    def run(
        self,
        argv: Sequence[str],
        *,
        env: dict[str, str] | None = None,
        input_bytes: bytes | None = None,
        cwd: str | None = None,
        on_start: Callable[[int], None] | None = None,
    ) -> JailResult:
        """`on_start` is called with the child's pid, which is also its process group, as soon as
        the child runs. If it raises, the child is killed and the error propagates."""
        if self.policy.enforce_network:
            return self._run_enforced(
                argv, env=env, input_bytes=input_bytes, cwd=cwd, on_start=on_start
            )
        return self._run(argv, env=env, input_bytes=input_bytes, cwd=cwd, on_start=on_start)

    def _run_enforced(
        self,
        argv: Sequence[str],
        *,
        env: dict[str, str] | None,
        input_bytes: bytes | None,
        cwd: str | None,
        on_start: Callable[[int], None] | None,
    ) -> JailResult:
        """Run argv behind the egress proxy, in a network namespace with no route out.

        The jail starts the bridge in the child first, and the bridge runs argv. The child reaches
        the network only through the proxy, so a client that ignores the proxy variables cannot
        connect at all. A host that cannot make the namespace refuses, rather than run open.
        """
        argv = [str(a) for a in argv]
        if not sys.platform.startswith("linux"):
            return JailResult(
                ok=False, refused="network enforcement needs Linux, so this host cannot run it"
            )
        if "net" not in _plan_namespaces(self.policy)[1]:
            return JailResult(
                ok=False,
                refused="network enforcement needs a network namespace, which this host lacks",
            )
        try:
            _check_shell_escape(argv, self.policy)
        except JailRefused as e:
            return JailResult(ok=False, refused=str(e), exit_code=None)
        allow = self.proxy_allow or Allow(
            hosts=frozenset(host.lower() for host in self.policy.network_allowlist)
        )
        scratch = Path(tempfile.mkdtemp(prefix="organism-egress-"))
        socket_path = scratch / "proxy.sock"
        proxy_url = f"http://127.0.0.1:{BRIDGE_PORT}"
        bridged = [
            sys.executable,
            "-I",
            str(BRIDGE),
            "--listen",
            f"127.0.0.1:{BRIDGE_PORT}",
            "--upstream",
            str(socket_path),
            "--",
            *argv,
        ]
        proxy_env = {
            **(env or {}),
            "HTTP_PROXY": proxy_url,
            "HTTPS_PROXY": proxy_url,
            "http_proxy": proxy_url,
            "https_proxy": proxy_url,
        }
        try:
            with EgressProxy(allow, socket_path=socket_path):
                return self._run(
                    bridged, env=proxy_env, input_bytes=input_bytes, cwd=cwd, on_start=on_start
                )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def _run(
        self,
        argv: Sequence[str],
        *,
        env: dict[str, str] | None = None,
        input_bytes: bytes | None = None,
        cwd: str | None = None,
        on_start: Callable[[int], None] | None = None,
    ) -> JailResult:
        argv = [str(a) for a in argv]
        try:
            _check_shell_escape(argv, self.policy)
        except JailRefused as e:
            return JailResult(ok=False, refused=str(e), exit_code=None)

        if self.policy.env_allowlist is not None:
            child_env = allowlisted_env(self.policy.env_allowlist, extra=env)
        else:
            child_env = dict(os.environ)
            if env:
                child_env.update(env)
            for prefix in self.policy.scrub_env_prefixes:
                for k in list(child_env):
                    if k.startswith(prefix) or k == prefix.rstrip("_"):
                        child_env.pop(k, None)
            child_env = without_stored(child_env)
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
                preexec_fn=preexec,  # noqa: PLW1509 -- rlimits apply before exec
                start_new_session=True,
            )
        except Exception as e:
            logger.warning("run failed", exc_info=True)
            return JailResult(
                ok=False,
                stderr=f"spawn_failed:{type(e).__name__}:{e}",
                degraded=degraded + [f"spawn_failed:{type(e).__name__}"],
                namespaces_attempted=ns_attempted,
                rlimits_applied=rlimits_applied,
            )

        if on_start is not None:
            try:
                on_start(proc.pid)
            except BaseException:
                _kill_group(proc)  # no caller knows this child, so nothing could stop it later
                raise

        timed_out = False
        try:
            stdout_b, stderr_b = proc.communicate(input=input_bytes, timeout=self.policy.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                logger.debug("run failed", exc_info=True)
                try:
                    proc.kill()
                except Exception:
                    logger.debug("run failed", exc_info=True)
            try:
                stdout_b, stderr_b = proc.communicate(timeout=2)
            except Exception:
                logger.debug("run failed", exc_info=True)
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
