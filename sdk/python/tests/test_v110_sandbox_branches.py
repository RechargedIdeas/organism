"""The sandbox branches that the other sandbox tests leave out (v1.10 sandbox, v1.12 W5 hardening).

Parent-side branches run on any host. A child's own setup (its namespace, loopback and rlimits) runs
in the forked child, which the coverage trace cannot see. Those are checked two ways: by effect, from
what a real child reports, and in-process, by calling the function the child would run, with a fake
libc. Linux-only branches are marked LINUX and skip elsewhere.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import signal
import struct
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, NoReturn

import pytest
from organism_sdk.sandbox import jail, runtime
from organism_sdk.sandbox.audit import SandboxAuditEvent
from organism_sdk.sandbox.jail import SETUP_FAILED_EXIT, SETUP_MARKER, ProcessJail, _setup_refusal
from organism_sdk.sandbox.policy import SandboxPolicy
from organism_sdk.sandbox.runtime import OrganismSandbox
from organism_sdk.trace import SandboxTraceEntry

LINUX = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only")
POSIX = pytest.mark.skipif(sys.platform == "win32", reason="rlimits are POSIX only")

CLONE_NEWUSER = 0x10000000
CLONE_NEWNS = 0x00020000
CLONE_NEWPID = 0x20000000
CLONE_NEWNET = 0x40000000
NAMESPACE = CLONE_NEWUSER | CLONE_NEWNS | CLONE_NEWNET

RLIMITS_CHILD = r"""
import json, resource
names = ["RLIMIT_AS", "RLIMIT_CPU", "RLIMIT_NOFILE", "RLIMIT_NPROC"]
print(json.dumps({n: list(resource.getrlimit(getattr(resource, n))) for n in names}))
"""

TUNNEL_CHILD = r"""
import os, socket
print(os.environ["HTTPS_PROXY"])
sock = socket.create_connection(("127.0.0.1", 3128), timeout=5)
sock.sendall(b"CONNECT evil.example.test:443 HTTP/1.1\r\nHost: evil.example.test:443\r\n\r\n")
print(sock.recv(64).split(b"\r\n")[0].decode())
"""


def _quick(**overrides: Any) -> SandboxPolicy:
    """A short policy that keeps the test child off the namespace path unless a test asks for it."""
    values: dict[str, Any] = {"timeout_s": 20, "use_namespaces": False, "label": "branches"}
    values.update(overrides)
    return SandboxPolicy(**values)


def _caps(monkeypatch: pytest.MonkeyPatch, *, linux: bool, unshare: bool) -> None:
    monkeypatch.delenv("ORGANISM_JAIL_FULL_NS", raising=False)
    monkeypatch.setattr(
        jail, "capabilities", lambda: {"linux": linux, "unshare": unshare, "rlimits": True}
    )


class _Tracer:
    def __init__(self) -> None:
        self.entries: list[SandboxTraceEntry] = []

    def emit_sandbox(self, entry: SandboxTraceEntry) -> None:
        self.entries.append(entry)


class _Exited(Exception):
    """Stands in for the child's os._exit, so the test sees the exit code instead of ending."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


class _FakeLibc:
    """A libc whose unshare returns as given, and sets errno the way a failed call does."""

    def __init__(self, result: int, errno: int = 0) -> None:
        self._result = result
        self._errno = errno

    def unshare(self, flags: int) -> int:
        ctypes.set_errno(self._errno)
        return self._result


def _exit_as_a_test(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_exit(code: int) -> NoReturn:
        raise _Exited(code)

    monkeypatch.setattr(os, "_exit", fake_exit)


# --- the runtime: tracer, outcomes, wrappers, self-check, generative compose -----------------------


def test_a_tracer_given_to_the_runtime_hears_its_audit_events() -> None:
    tracer = _Tracer()
    sandbox = OrganismSandbox(policy=_quick(), tracer=tracer)
    sandbox.audit.record(SandboxAuditEvent(action="ok", label="traced"))
    assert [entry.label for entry in tracer.entries] == ["traced"]


@pytest.mark.parametrize(
    ("argv", "policy", "action"),
    [
        ([sys.executable, "-c", "print('fine')"], _quick(label="ok-case"), "ok"),
        ([sys.executable, "-c", "import sys; sys.exit(3)"], _quick(label="error-case"), "error"),
        (
            [sys.executable, "-c", "import time; time.sleep(5)"],
            _quick(label="timeout-case", timeout_s=0.3),
            "timeout",
        ),
        (
            ["/bin/sh", "-c", "echo pwned"],
            _quick(label="refuse-case", deny_shell_escape=True),
            "refuse",
        ),
    ],
)
def test_each_outcome_is_recorded_under_its_own_action(
    argv: list[str], policy: SandboxPolicy, action: str
) -> None:
    sandbox = OrganismSandbox(policy=_quick())
    sandbox.run(argv, policy=policy)
    last = sandbox.audit.recent(1)[0]
    assert last["action"] == action
    assert last["label"] == policy.label


def test_run_python_uses_the_runtime_policy_when_none_is_passed() -> None:
    sandbox = OrganismSandbox(policy=_quick(label="runtime-policy"))
    result = sandbox.run_python("print('own policy')")
    assert result.ok, result.stderr
    assert result.stdout.strip() == "own policy"
    assert sandbox.audit.recent(1)[0]["label"] == "runtime-policy"


def test_wrap_self_runs_the_child_under_the_self_containment_policy() -> None:
    sandbox = OrganismSandbox(policy=_quick())
    result = sandbox.wrap_self([sys.executable, "-c", "print('inside')"])
    assert result.ok, result.stderr
    assert result.stdout.strip() == "inside"
    assert sandbox.audit.recent(1)[0]["label"] == "self_containment"


def test_status_says_whether_this_process_is_inside_a_jail(monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox = OrganismSandbox(policy=_quick())
    monkeypatch.setenv("ORGANISM_IN_JAIL", "yes")
    assert sandbox.status().in_jail is True
    monkeypatch.setenv("ORGANISM_IN_JAIL", "0")
    assert sandbox.status().in_jail is False


def test_self_check_reports_a_check_that_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "capabilities", lambda: {"spawn": False, "docker_required": False})
    sandbox = OrganismSandbox(policy=_quick())
    result = sandbox.self_check()
    assert result.ok is False
    assert result.checks[0]["id"] == "capabilities"
    assert result.checks[0]["ok"] is False
    last = sandbox.audit.recent(1)[0]
    assert last["action"] == "self_check"
    assert last["ok"] is False


def test_run_generative_source_runs_the_draft_in_the_jail(monkeypatch: pytest.MonkeyPatch) -> None:
    # The draft runs in a cold spawn child. Under load that start has exceeded the 2 s default.
    monkeypatch.setenv("ORGANISM_SANDBOX_TIMEOUT_S", "30")
    sandbox = OrganismSandbox(policy=_quick())
    payload = sandbox.run_generative_source("def main(a):\n    return a * 2\n", args={"a": 21})
    assert payload["ok"] is True, payload
    assert payload["value"] == 42
    assert payload["runtime_sandbox"] == "organism_native"
    assert payload["docker_required"] is False
    assert sandbox.audit.recent(1)[0]["label"] == "generative_compose"


def test_run_generative_source_refuses_an_unsafe_draft() -> None:
    sandbox = OrganismSandbox(policy=_quick())
    payload = sandbox.run_generative_source("import os\ndef main():\n    return 1\n")
    assert payload["ok"] is False
    assert payload["error"].startswith("SandboxRefused")


# --- the jail: the setup reason, planning, shell check, environment, failures ----------------------


def test_a_setup_reason_is_read_only_from_a_child_that_failed_its_setup() -> None:
    reason = "the network namespace could not be made: Operation not permitted"
    assert _setup_refusal(SETUP_FAILED_EXIT, f"{SETUP_MARKER}{reason}\nmore") == reason
    assert _setup_refusal(SETUP_FAILED_EXIT, "no marker here") is None
    assert _setup_refusal(0, f"{SETUP_MARKER}why\n") is None
    assert _setup_refusal(None, f"{SETUP_MARKER}why\n") is None


def test_a_policy_that_turns_namespaces_off_plans_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _caps(monkeypatch, linux=True, unshare=True)
    # OC-5: network isolation was wanted, so the plan says so even with namespaces off.
    assert jail._plan_namespaces(_quick(use_namespaces=False)) == (
        0, [], ["network_not_namespaced", "isolation_not_claimed"]
    )
    assert jail._plan_namespaces(
        _quick(use_namespaces=False, allow_network=True, isolate_network=False)
    ) == (0, [], [])


def test_a_host_that_is_not_linux_plans_no_namespaces(monkeypatch: pytest.MonkeyPatch) -> None:
    _caps(monkeypatch, linux=False, unshare=False)
    plan = jail._plan_namespaces(_quick(use_namespaces=True))
    assert plan == (
        0,
        [],
        ["namespaces_unavailable_non_linux", "network_not_namespaced", "isolation_not_claimed"],
    )


def test_a_linux_host_without_unshare_plans_no_namespaces(monkeypatch: pytest.MonkeyPatch) -> None:
    _caps(monkeypatch, linux=True, unshare=False)
    plan = jail._plan_namespaces(_quick(use_namespaces=True))
    assert plan == (
        0,
        [],
        ["unshare_unavailable", "network_not_namespaced", "isolation_not_claimed"],
    )


def test_the_default_plan_isolates_the_network_without_full_ns_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # OC-5: allow_network=False → plan user+mount+net; ORGANISM_JAIL_FULL_NS not required.
    _caps(monkeypatch, linux=True, unshare=True)
    flags, attempted, degraded = jail._plan_namespaces(_quick(use_namespaces=True))
    assert attempted == ["user", "mount", "net"]
    assert flags == CLONE_NEWUSER | CLONE_NEWNS | CLONE_NEWNET
    assert degraded == []


def test_enforcing_the_network_adds_its_namespace_and_full_mode_adds_pid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _caps(monkeypatch, linux=True, unshare=True)
    flags, attempted, degraded = jail._plan_namespaces(
        _quick(use_namespaces=True, enforce_network=True, allow_network=True, isolate_network=False)
    )
    assert attempted == ["user", "mount", "net"]
    assert flags & CLONE_NEWNET
    assert degraded == []
    monkeypatch.setenv("ORGANISM_JAIL_FULL_NS", "1")
    flags, attempted, _ = jail._plan_namespaces(
        _quick(use_namespaces=True, allow_network=True, isolate_network=False)
    )
    assert attempted == ["user", "mount", "pid", "net"]
    assert flags & CLONE_NEWPID
    assert flags & CLONE_NEWNET


def test_allow_network_without_isolate_skips_net_and_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _caps(monkeypatch, linux=True, unshare=True)
    _flags, attempted, degraded = jail._plan_namespaces(
        _quick(use_namespaces=True, allow_network=True, isolate_network=False)
    )
    assert attempted == ["user", "mount"]
    assert "net" not in attempted
    assert degraded == []


def test_a_host_whose_libc_cannot_load_reports_no_unshare(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_libc(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("libc.so.6 missing")

    monkeypatch.setattr(ctypes, "CDLL", no_libc)
    assert jail.capabilities()["unshare"] is False


def test_without_the_resource_module_the_child_still_runs_and_says_rlimits_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "resource", None)
    assert jail.has_resource_module() is False
    assert jail.capabilities()["rlimits"] is False
    result = ProcessJail(_quick(max_rss_mb=256)).run([sys.executable, "-c", "print('ran')"])
    assert result.ok, result.stderr
    assert result.stdout.strip() == "ran"
    assert "rlimits_unavailable" in result.degraded
    assert result.rlimits_applied == []


def test_the_shell_check_does_nothing_when_the_policy_allows_shells() -> None:
    jail._check_shell_escape(["/bin/sh", "-c", "id"], _quick(deny_shell_escape=False))


def test_an_interpreter_asked_to_run_a_shell_by_code_is_refused() -> None:
    with pytest.raises(jail.JailRefused, match="pattern=os.system"):
        jail._check_shell_escape([sys.executable, "-c", "import os; os.system('id')"], _quick())


def test_a_shell_pattern_without_dash_c_is_not_refused() -> None:
    jail._check_shell_escape([sys.executable, "os.system"], _quick())


def test_an_env_allowlist_passes_only_the_named_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORGANISM_BRANCH_KEEP", "kept")
    monkeypatch.setenv("ORGANISM_BRANCH_DROP", "dropped")
    policy = _quick(env_allowlist=("ORGANISM_BRANCH_KEEP",), label="env")
    code = "import json, os; print(json.dumps(dict(os.environ)))"
    result = ProcessJail(policy).run(
        [sys.executable, "-c", code], env={"ORGANISM_BRANCH_EXTRA": "added"}
    )
    assert result.ok, result.stderr
    child = json.loads(result.stdout)
    assert child["ORGANISM_BRANCH_KEEP"] == "kept"
    assert child["ORGANISM_BRANCH_EXTRA"] == "added"
    assert "ORGANISM_BRANCH_DROP" not in child
    assert child["ORGANISM_IN_JAIL"] == "1"


def test_scrubbed_prefixes_leave_neither_their_variables_nor_the_bare_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORGANISM_BRANCH_SECRET_TOKEN", "x")
    monkeypatch.setenv("ORGANISM_BRANCH_SECRET", "y")
    monkeypatch.setenv("ORGANISM_BRANCH_KEEP", "kept")
    policy = _quick(scrub_env_prefixes=("ORGANISM_BRANCH_SECRET_",), label="scrub")
    code = "import json, os; print(json.dumps(dict(os.environ)))"
    result = ProcessJail(policy).run([sys.executable, "-c", code])
    assert result.ok, result.stderr
    child = json.loads(result.stdout)
    assert "ORGANISM_BRANCH_SECRET_TOKEN" not in child
    assert "ORGANISM_BRANCH_SECRET" not in child
    assert child["ORGANISM_BRANCH_KEEP"] == "kept"


def test_a_child_that_cannot_be_started_is_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_fork(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("no fork")

    monkeypatch.setattr(subprocess, "Popen", no_fork)
    result = ProcessJail(_quick()).run([sys.executable, "-c", "pass"])
    assert result.ok is False
    assert result.pid is None
    assert result.stderr == "spawn_failed:OSError:no fork"
    assert "spawn_failed:OSError" in result.degraded


def test_a_caller_that_cannot_take_the_child_gets_it_killed_and_its_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    killed: list[subprocess.Popen[bytes]] = []
    real_kill_group = jail._kill_group

    def record(proc: subprocess.Popen[bytes]) -> None:
        killed.append(proc)
        real_kill_group(proc)

    def refuse(_pid: int) -> None:
        raise RuntimeError("the ticket was stopped")

    monkeypatch.setattr(jail, "_kill_group", record)
    with pytest.raises(RuntimeError, match="the ticket was stopped"):
        ProcessJail(_quick(timeout_s=60)).run(
            [sys.executable, "-c", "import time; time.sleep(60)"], on_start=refuse
        )
    assert len(killed) == 1
    assert killed[0].returncode is not None


def test_a_timed_out_child_is_still_stopped_when_its_group_cannot_be_signalled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_group(*_args: Any) -> None:
        raise PermissionError("no group")

    monkeypatch.setattr(os, "killpg", no_group, raising=False)
    result = ProcessJail(_quick(timeout_s=0.5)).run(
        [sys.executable, "-c", "import time; time.sleep(60)"]
    )
    assert result.timed_out is True
    assert result.ok is False


@POSIX
def test_a_permission_error_on_the_childs_stderr_does_not_change_what_it_applied() -> None:
    code = "import sys; sys.stderr.write('Operation not permitted\\n')"
    policy = SandboxPolicy(timeout_s=20, label="partial", use_namespaces=False)
    result = ProcessJail(policy).run([sys.executable, "-c", code])
    assert result.ok, result.stderr
    assert "RLIMIT_AS" in result.rlimits_applied
    assert "namespace_or_rlimit_partial" not in result.degraded


@POSIX
def test_a_limit_the_kernel_refuses_is_not_reported_as_applied() -> None:
    result = ProcessJail(_quick(max_rss_mb=2**50, label="refused")).run(
        [sys.executable, "-c", "print('ran')"]
    )
    assert result.ok, result.stderr
    assert result.stdout.strip() == "ran"
    assert "RLIMIT_AS" not in result.rlimits_applied
    assert "RLIMIT_CPU" in result.rlimits_applied
    assert "namespace_or_rlimit_partial" in result.degraded


def test_killing_the_group_of_a_child_that_already_ended_is_not_an_error() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    jail._kill_group(proc)
    assert proc.returncode == 0


# --- the child's own setup, by effect: what a real child reports -----------------------------------


@POSIX
def test_the_child_gets_the_rlimits_its_policy_names() -> None:
    policy = _quick(max_rss_mb=512, cpu_time_s=30, max_fds=64, max_nproc=128)
    result = ProcessJail(policy).run([sys.executable, "-c", RLIMITS_CHILD])
    assert result.ok, result.stderr
    limits = json.loads(result.stdout)
    assert limits["RLIMIT_AS"] == [512 * 1024 * 1024, 512 * 1024 * 1024]
    assert limits["RLIMIT_CPU"] == [30, 31]
    assert limits["RLIMIT_NOFILE"] == [64, 64]
    assert limits["RLIMIT_NPROC"] == [128, 128]


@POSIX
def test_a_limit_the_host_cannot_set_is_skipped_and_the_child_still_runs() -> None:
    result = ProcessJail(_quick(max_fds=2**70)).run([sys.executable, "-c", RLIMITS_CHILD])
    assert result.ok, result.stderr
    soft, _hard = json.loads(result.stdout)["RLIMIT_NOFILE"]
    assert soft != 2**70


# --- the child's own setup, in-process: the function the forked child runs ------------------------


@LINUX
def test_a_child_that_cannot_make_its_namespace_says_why_and_exits_before_exec(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ctypes, "CDLL", lambda *_a, **_k: _FakeLibc(-1, errno=1))
    _exit_as_a_test(monkeypatch)
    preexec = jail._make_preexec(SandboxPolicy(enforce_network=True, label="t"), NAMESPACE)
    with pytest.raises(_Exited) as exited:
        preexec()
    assert exited.value.code == SETUP_FAILED_EXIT
    err = capfd.readouterr().err
    assert err.startswith(SETUP_MARKER + "the network namespace could not be made: ")
    assert "Operation not permitted" in err


@LINUX
def test_a_namespace_failure_with_no_errno_gives_the_bare_reason(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ctypes, "CDLL", lambda *_a, **_k: _FakeLibc(-1, errno=0))
    _exit_as_a_test(monkeypatch)
    preexec = jail._make_preexec(SandboxPolicy(enforce_network=True, label="t"), NAMESPACE)
    with pytest.raises(_Exited):
        preexec()
    assert capfd.readouterr().err == SETUP_MARKER + "the network namespace could not be made\n"


@LINUX
def test_a_child_whose_libc_cannot_load_says_so(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    def no_libc(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("libc.so.6 missing")

    monkeypatch.setattr(ctypes, "CDLL", no_libc)
    _exit_as_a_test(monkeypatch)
    preexec = jail._make_preexec(SandboxPolicy(enforce_network=True, label="t"), NAMESPACE)
    with pytest.raises(_Exited):
        preexec()
    expected = SETUP_MARKER + "the network namespace could not be made: libc.so.6 missing\n"
    assert capfd.readouterr().err == expected


@LINUX
def test_a_child_whose_loopback_cannot_come_up_says_so_in_process(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ctypes, "CDLL", lambda *_a, **_k: _FakeLibc(0))

    def no_loopback() -> None:
        raise OSError("no loopback")

    monkeypatch.setattr(jail, "_bring_up_loopback", no_loopback)
    _exit_as_a_test(monkeypatch)
    preexec = jail._make_preexec(SandboxPolicy(enforce_network=True, label="t"), NAMESPACE)
    with pytest.raises(_Exited):
        preexec()
    expected = SETUP_MARKER + "loopback could not be brought up: no loopback\n"
    assert capfd.readouterr().err == expected


@LINUX
def test_a_child_whose_setup_succeeds_goes_on_to_exec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ctypes, "CDLL", lambda *_a, **_k: _FakeLibc(0))
    monkeypatch.setattr(jail, "_bring_up_loopback", lambda: None)
    policy = SandboxPolicy(
        enforce_network=True,
        label="t",
        max_rss_mb=None,
        cpu_time_s=None,
        max_fds=None,
        max_nproc=None,
    )
    assert jail._make_preexec(policy, NAMESPACE)() is None


@LINUX
def test_without_enforcement_a_failed_namespace_is_not_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ctypes, "CDLL", lambda *_a, **_k: _FakeLibc(-1, errno=1))
    policy = SandboxPolicy(
        enforce_network=False,
        label="t",
        max_rss_mb=None,
        cpu_time_s=None,
        max_fds=None,
        max_nproc=None,
    )
    assert jail._make_preexec(policy, NAMESPACE)() is None


# --- enforced runs refuse where they cannot be enforced -------------------------------------------


def test_enforcement_refuses_on_a_host_that_is_not_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jail, "sys", SimpleNamespace(platform="win32"))
    result = ProcessJail(SandboxPolicy(enforce_network=True, label="t")).run(
        [sys.executable, "-c", "pass"]
    )
    assert result.ok is False
    assert "needs Linux" in (result.refused or "")


@LINUX
def test_enforcement_refuses_when_the_namespace_is_not_planned() -> None:
    policy = SandboxPolicy(enforce_network=True, use_namespaces=False, label="t")
    result = ProcessJail(policy).run([sys.executable, "-c", "pass"])
    assert result.ok is False
    assert "network namespace" in (result.refused or "")


@LINUX
def test_enforcement_refuses_a_shell_before_it_starts() -> None:
    result = ProcessJail(SandboxPolicy(enforce_network=True, label="t")).run(
        ["/bin/sh", "-c", "id"]
    )
    assert result.ok is False
    assert "shell escape" in (result.refused or "")


@LINUX
def test_without_a_test_allowlist_the_policy_proxy_still_refuses_a_host_off_its_list() -> None:
    policy = SandboxPolicy(
        timeout_s=30,
        label="policy-allow",
        network_allowlist=["localhost"],
        allow_network=True,
        enforce_network=True,
    )
    result = ProcessJail(policy).run([sys.executable, "-c", TUNNEL_CHILD])
    assert result.ok, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "http://127.0.0.1:3128"
    assert lines[1].startswith("HTTP/1.1 403")


def test_the_child_side_does_nothing_more_when_there_is_no_resource_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "resource", None)
    assert jail._make_preexec(_quick(max_rss_mb=256), 0)() is None


@POSIX
def test_the_child_side_sets_each_limit_it_is_given_and_skips_one_the_host_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = pytest.importorskip("resource")

    calls: list[tuple[int, tuple[int, int]]] = []

    def setrlimit(which: int, limits: tuple[int, int]) -> None:
        if which == resource.RLIMIT_CPU:
            raise ValueError("refused by the host")
        calls.append((which, limits))

    monkeypatch.setattr(resource, "setrlimit", setrlimit)
    policy = SandboxPolicy(label="t", max_rss_mb=512, cpu_time_s=30, max_fds=64, max_nproc=128)
    assert jail._make_preexec(policy, 0)() is None
    mib = 1024 * 1024
    assert calls == [
        (resource.RLIMIT_AS, (512 * mib, 512 * mib)),
        (resource.RLIMIT_NOFILE, (64, 64)),
        (resource.RLIMIT_NPROC, (128, 128)),
    ]


@POSIX
def test_a_child_whose_host_refuses_every_limit_still_gets_to_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = pytest.importorskip("resource")

    def refuse(_which: int, _limits: tuple[int, int]) -> None:
        raise ValueError("refused by the host")

    monkeypatch.setattr(resource, "setrlimit", refuse)
    policy = SandboxPolicy(label="t", max_rss_mb=512, cpu_time_s=30, max_fds=64, max_nproc=128)
    assert jail._make_preexec(policy, 0)() is None


def test_the_loopback_refuses_to_come_up_off_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jail, "sys", SimpleNamespace(platform="win32"))
    with pytest.raises(OSError, match="only be brought up on Linux"):
        jail._bring_up_loopback()


@LINUX
def test_the_loopback_gets_the_up_flag_added_to_the_flags_it_has(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fcntl  # Linux only, so not at module level

    sent: list[tuple[int, bytes]] = []

    def ioctl(_sock: object, request: int, arg: bytes) -> bytes:
        sent.append((request, arg))
        return struct.pack(jail.IFREQ, b"lo", 0x8)

    monkeypatch.setattr(fcntl, "ioctl", ioctl)
    jail._bring_up_loopback()
    assert [request for request, _ in sent] == [jail.SIOCGIFFLAGS, jail.SIOCSIFFLAGS]
    assert struct.unpack(jail.IFREQ, sent[1][1])[1] == 0x8 | jail.IFF_UP


def test_a_timed_out_child_that_cannot_be_killed_gives_no_output_and_no_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse_group(*_args: Any) -> None:
        raise PermissionError("no group")

    def refuse_kill(_proc: subprocess.Popen[bytes]) -> None:
        raise PermissionError("no kill")

    pids: list[int] = []
    monkeypatch.setattr(os, "killpg", refuse_group, raising=False)
    monkeypatch.setattr(subprocess.Popen, "kill", refuse_kill)
    try:
        result = ProcessJail(_quick(timeout_s=0.5)).run(
            [sys.executable, "-c", "import time; time.sleep(60)"], on_start=pids.append
        )
    finally:
        # The test left the child running on purpose, so end it here.
        for pid in pids:
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGTERM)
    assert result.timed_out is True
    assert result.ok is False
    assert result.stdout == ""
