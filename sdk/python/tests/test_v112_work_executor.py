"""v1.12 W5, the Executor: what it refuses, where it runs, how slots are held, and recovery.

Most tests use a fake jail, so they run on any host. The one test that runs the real jail is
Linux only, where containment exists.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from organism_sdk.sandbox.jail import JailResult, ProcessJail
from organism_sdk.sandbox.policy import SandboxPolicy
from organism_sdk.work import operator
from organism_sdk.work.domain import (
    Assignment,
    AssignmentState,
    Mandate,
    Strength,
    Ticket,
    Via,
)
from organism_sdk.work.executors import (
    RECOVERY,
    ProcessExecutor,
    Slots,
    recover,
    ticket_directory,
)
from organism_sdk.work.store import WorkStore


class FakeJail:
    """Records each run and answers from a queue of results, or with a clean success."""

    def __init__(self, calls: list[dict[str, Any]], results: list[JailResult]) -> None:
        self.calls = calls
        self.results = results

    def __call__(self, policy: SandboxPolicy) -> FakeJail:
        self.policy = policy
        return self

    def run(
        self,
        argv: Sequence[str],
        *,
        env: dict[str, str] | None = None,
        input_bytes: bytes | None = None,
        cwd: str | None = None,
    ) -> JailResult:
        self.calls.append({"argv": list(argv), "cwd": cwd, "timeout_s": self.policy.timeout_s})
        return self.results.pop(0) if self.results else JailResult(ok=True, exit_code=0)


@pytest.fixture
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")


def executor(
    root: Path,
    calls: list[dict[str, Any]],
    results: list[JailResult] | None = None,
    **options: Any,
) -> ProcessExecutor:
    return ProcessExecutor(
        root,
        argv=options.pop("argv", ["claude", "-p", "do the work"]),
        slots=options.pop("slots", Slots(3)),
        prepare=options.pop("prepare", None),
        jail=FakeJail(calls, results or []),
        containment_check=options.pop("containment_check", lambda: None),
        slot_wait_s=options.pop("slot_wait_s", 0.05),
        **options,
    )


def test_a_blocked_program_is_refused_before_anything_runs(tmp_path: Path, key: None) -> None:
    calls: list[dict[str, Any]] = []
    for argv in (["sudo", "claude"], [r"C:\Tools\SSH.exe", "host"]):
        result = executor(tmp_path, calls, argv=argv).run("t-1")
        assert result.ok is False
        assert "blocked" in (result.refused or "")
    assert calls == []


def test_no_containment_means_no_run(tmp_path: Path, key: None) -> None:
    calls: list[dict[str, Any]] = []
    runner = executor(tmp_path, calls, containment_check=lambda: "containment needs Linux")
    result = runner.run("t-1")
    assert result.refused == "containment needs Linux"
    assert calls == []


def test_a_missing_key_is_named_and_its_value_is_never_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    calls: list[dict[str, Any]] = []
    result = executor(tmp_path, calls).run("t-1")
    assert result.refused == "none of the variables the profile passes is set: ANTHROPIC_API_KEY"
    assert calls == []


@pytest.mark.parametrize("ticket_id", ["../escape", "a/b", "", ".hidden", "x" * 200])
def test_an_unsafe_ticket_id_is_refused_before_anything_runs(
    tmp_path: Path, key: None, ticket_id: str
) -> None:
    calls: list[dict[str, Any]] = []
    result = executor(tmp_path, calls).run(ticket_id)
    assert result.ok is False
    assert "not a safe directory name" in (result.refused or "")
    assert calls == []


def test_the_run_uses_the_tickets_own_directory(tmp_path: Path, key: None) -> None:
    calls: list[dict[str, Any]] = []
    result = executor(tmp_path, calls).run("t-42")
    assert result.ok is True
    assert calls == [
        {
            "argv": ["claude", "-p", "do the work"],
            "cwd": str(tmp_path / "t-42"),
            "timeout_s": 1800.0,
        }
    ]
    assert (tmp_path / "t-42").is_dir()
    assert result.workdir == str(tmp_path / "t-42")


def test_prepare_runs_first_with_its_own_limit(tmp_path: Path, key: None) -> None:
    calls: list[dict[str, Any]] = []
    runner = executor(tmp_path, calls, prepare=["git", "init"])
    assert runner.run("t-7").ok is True
    assert [call["argv"] for call in calls] == [["git", "init"], ["claude", "-p", "do the work"]]
    assert calls[0]["timeout_s"] == 600.0
    assert calls[1]["timeout_s"] == 1800.0


def test_a_failed_prepare_stops_the_run(tmp_path: Path, key: None) -> None:
    calls: list[dict[str, Any]] = []
    failed = JailResult(ok=False, exit_code=2, stderr="no repository")
    result = executor(tmp_path, calls, [failed], prepare=["git", "clone"]).run("t-8")
    assert result.ok is False
    assert result.exit_code == 2
    assert [call["argv"] for call in calls] == [["git", "clone"]]


def test_a_timeout_comes_back_as_a_timeout(tmp_path: Path, key: None) -> None:
    calls: list[dict[str, Any]] = []
    slow = JailResult(ok=False, timed_out=True, exit_code=None)
    result = executor(tmp_path, calls, [slow]).run("t-9")
    assert result.ok is False
    assert result.timed_out is True


def test_ticket_work_leaves_the_person_reserve_alone(tmp_path: Path, key: None) -> None:
    calls: list[dict[str, Any]] = []
    slots = Slots(2, reserve=1)
    assert slots.acquire(person=False, timeout=0.01) is True  # one ticket run is in flight
    runner = executor(tmp_path, calls, slots=slots)
    refused = runner.run("t-blocked")
    assert refused.refused == "no worker slot is free"
    assert calls == []
    answered = runner.run("t-person", person=True)  # a person's message may take the reserve
    assert answered.ok is True
    assert slots.free == 1  # the person's slot is returned when the run ends


def test_slots_never_go_below_zero_or_above_capacity() -> None:
    slots = Slots(1, reserve=0)
    assert slots.acquire(person=False, timeout=0.01) is True
    assert slots.acquire(person=False, timeout=0.01) is False
    slots.release()
    assert slots.free == 1
    with pytest.raises(ValueError):
        Slots(1, reserve=1)
    with pytest.raises(ValueError):
        Slots(0)


def test_a_ticket_directory_stays_under_its_root(tmp_path: Path) -> None:
    assert ticket_directory(tmp_path, "t-1.a_b") == tmp_path / "t-1.a_b"
    with pytest.raises(ValueError):
        ticket_directory(tmp_path, "..")


def test_the_executor_needs_an_argv(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ProcessExecutor(tmp_path, argv=[], slots=Slots(2))


def open_ticket(store: WorkStore, ticket_id: str, state: AssignmentState) -> None:
    mandate = Mandate(
        policy_version="sha256:test",
        strength=Strength.EXPLICIT,
        via=Via.ADDRESSED,
        source="github",
        row="repo",
        sender="alice",
        rules=("ci-fix",),
    )
    assignment = Assignment(id=f"a-{ticket_id}", ticket_id=ticket_id, state=state)
    store.save_ticket(Ticket(id=ticket_id, mandate=mandate, assignment=assignment))
    store.save_assignment(assignment)


def test_a_restart_ends_running_assignments_and_queues_one_note(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    with WorkStore(path) as store:
        open_ticket(store, "t-run", AssignmentState.RUNNING)
        open_ticket(store, "t-idle", AssignmentState.PENDING)
        assert recover(store) == ["t-run"]
        states = {
            a.ticket_id: a.state for t in ("t-run", "t-idle") for a in store.assignments_of(t)
        }
        assert states == {"t-run": AssignmentState.ENDED, "t-idle": AssignmentState.PENDING}
        assert [e.kind for e in store.pending_effects()] == [RECOVERY]
        assert recover(store) == []  # the second restart finds nothing running
        items = operator.attention(store)
        assert {
            "kind": "recovery",
            "id": "t-run",
            "detail": "a run was interrupted by a restart; rerun it or stop it",
        } in items


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the jail's containment is Linux")
def test_the_real_jail_gives_the_child_only_the_allowed_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setenv("WORK_TEST_OTHER", "must-not-pass")
    script = (
        "import os; print(sorted(k for k in os.environ"
        " if k.startswith(('ANTHROPIC', 'WORK_TEST'))))"
    )
    policy = replace(SandboxPolicy.work_executor(), timeout_s=30.0)
    runner = ProcessExecutor(
        tmp_path,
        argv=[sys.executable, "-c", script],
        slots=Slots(2),
        policy=policy,
        jail=ProcessJail,
        slot_wait_s=1.0,
    )
    result = runner.run("t-real")
    assert result.ok is True, result.stderr
    assert "ANTHROPIC_API_KEY" in result.stdout
    assert "WORK_TEST_OTHER" not in result.stdout
