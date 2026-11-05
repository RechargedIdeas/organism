"""v1.12 W5, the Ticket driver: accepted Decisions become Tickets, and Tickets run through the Executor.

Most tests use a fake Executor, so they run on any host. The one test that runs the real jail is
Linux only, where containment exists.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from organism_sdk import cli
from organism_sdk.work import codec, operator
from organism_sdk.work.assess import RuleAssessor
from organism_sdk.work.domain import (
    Addressed,
    Assignment,
    AssignmentState,
    Decision,
    Mandate,
    Outcome,
    Strength,
    Ticket,
    Trigger,
    Via,
    decision_key,
)
from organism_sdk.work.driver import DriveReport, drive, open_accepted, task_for, ticket_id_for
from organism_sdk.work.executors import SLOT_BUSY, Execution, ProcessExecutor, load_executor
from organism_sdk.work.gate import ScopeFacts
from organism_sdk.work.policy import AcceptMode, AdmissionRow, Policy, Rule, SourcePolicy
from organism_sdk.work.runner import evaluate
from organism_sdk.work.stage import Stage, stage_of
from organism_sdk.work.store import WorkStore

CI = Rule(id="ci-fix", instruction="fix failing CI", pattern="CI", auto=True)
POLICY = Policy(
    mode=AcceptMode.AUTO,
    rules=(CI,),
    sources=(
        SourcePolicy(source="github", allowed=frozenset({"alice"}), rows={"repo": AdmissionRow()}),
    ),
)
OBSERVED = ScopeFacts(listened=True, observed=True, row="repo")
MANDATE = Mandate(
    policy_version=POLICY.version,
    strength=Strength.EXPLICIT,
    via=Via.ADDRESSED,
    source="github",
    row="repo",
    sender="alice",
)


def message(n: int, text: str, *, thread: str = "github:issue-1", addressed: Addressed) -> Trigger:
    return Trigger(
        id=f"m{n}",
        source="github",
        thread=thread,
        actor="alice",
        human=True,
        addressed=addressed,
        at=f"2026-11-04T00:00:{n:02d}Z",
        text=text,
    )


def store_with(path: Path, *triggers: Trigger, pol: Policy = POLICY) -> None:
    """A store with the Policy in force, and each Trigger received and evaluated."""
    with WorkStore(path) as store:
        store.save_policy(pol, signature=b"approved in test")
        store.set_active_policy(pol.version)
        for trigger in triggers:
            store.receive(trigger)
        evaluate(store, pol, RuleAssessor(pol.rules), lambda _: OBSERVED)


def opener(path: Path) -> Callable[[], WorkStore]:
    return lambda: WorkStore(path)


class FakeExecutor:
    """Answers each run from a queue of Executions, or with a clean success once the queue is empty."""

    def __init__(
        self,
        results: list[Execution] | None = None,
        *,
        halt: str | None = None,
        during: Callable[[str], None] | None = None,
    ) -> None:
        self.results = list(results or [])
        self.halt = halt
        self.during = during
        self.runs: list[tuple[str, str]] = []

    def blocked_reason(self) -> str | None:
        return self.halt

    def run(self, ticket_id: str, *, person: bool = False, task: str = "") -> Execution:
        self.runs.append((ticket_id, task))
        if self.during is not None:
            self.during(ticket_id)
        if self.results:
            return self.results.pop(0)
        return Execution(ticket_id, ok=True, exit_code=0)


class ExplodingExecutor(FakeExecutor):
    """Raises for the first Ticket it is asked to run, and succeeds for the rest."""

    def run(self, ticket_id: str, *, person: bool = False, task: str = "") -> Execution:
        self.runs.append((ticket_id, task))
        if len(self.runs) == 1:
            raise RuntimeError("the runner broke")
        return Execution(ticket_id, ok=True, exit_code=0)


def ticket_state(path: Path, ticket_id: str) -> tuple[AssignmentState | None, object]:
    with WorkStore(path) as store:
        ticket = store.ticket(ticket_id)
        assert ticket is not None
        assignment = ticket.assignment
        state = None if assignment is None else assignment.state
        return state, ticket.latest_report


def test_an_accepted_decision_opens_one_ticket_with_its_mandate(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    store_with(path, message(1, "CI is red on the branch", addressed=Addressed.NONE))
    with WorkStore(path) as store:
        decision = store.all_decisions()[0]
        assert decision.outcome is Outcome.ACCEPT
        opened, held = open_accepted(store)
        assert held == []
        assert opened == [ticket_id_for(decision.id)]
        ticket = store.ticket(opened[0])
        assert ticket is not None
        assert ticket.mandate == decision.mandate
        assert ticket.mandate is not None
        assert ticket.mandate.via is Via.ADMISSION
        assert ticket.mandate.strength is Strength.INFERRED
        assert ticket.mandate.rules == ("ci-fix",)
        assert ticket.mandate.row == "repo"
        assert ticket.mandate.sender == "alice"
        assert ticket.thread == "github:issue-1"
        assert ticket.trigger_id == "m1"
        assert ticket.assignment == Assignment(
            id=f"{opened[0]}-a1", ticket_id=opened[0], state=AssignmentState.PENDING
        )
        assert open_accepted(store) == ([], [])  # a second pass opens nothing


def test_an_explicit_request_opens_a_ticket_with_no_rules(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    store_with(path, message(1, "please look at this", addressed=Addressed.MENTION))
    with WorkStore(path) as store:
        decision = store.all_decisions()[0]
        assert decision.mandate is not None
        assert decision.mandate.strength is Strength.EXPLICIT
        assert decision.mandate.via is Via.ADDRESSED
        assert decision.mandate.rules == ()


def test_an_ignored_decision_opens_nothing(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    store_with(path, message(1, "nothing to see here", addressed=Addressed.NONE))
    with WorkStore(path) as store:
        assert store.all_decisions()[0].outcome is Outcome.IGNORE
        assert open_accepted(store) == ([], [])


def test_a_decision_stored_without_a_mandate_is_not_opened(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    with WorkStore(path) as store:
        store.save_policy(POLICY, signature=b"approved in test")
        store.set_active_policy(POLICY.version)
        store.receive(message(1, "CI is red", addressed=Addressed.NONE))
        store.save_decision(
            Decision(
                id=decision_key("m1", POLICY.version),
                trigger_id="m1",
                outcome=Outcome.ACCEPT,
                reasons=("cell_inferred",),
            )
        )
        assert open_accepted(store) == ([], [])


def test_a_second_accepted_request_on_an_owned_thread_is_held_until_the_thread_is_free(
    tmp_path: Path,
) -> None:
    path = tmp_path / "work.sqlite"
    store_with(
        path,
        message(1, "please fix it", addressed=Addressed.MENTION),
        message(2, "and this too", addressed=Addressed.MENTION),
    )
    with WorkStore(path) as store:
        opened, held = open_accepted(store)
        assert len(opened) == 1
        assert len(held) == 1
        operator.stop(store, opened[0])
        reopened, still_held = open_accepted(store)
        assert reopened == [ticket_id_for(held[0])]
        assert still_held == []


def test_a_stopped_ticket_is_not_opened_again(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    store_with(path, message(1, "CI is red", addressed=Addressed.NONE))
    with WorkStore(path) as store:
        (ticket_id,), _ = open_accepted(store)
        operator.stop(store, ticket_id)
        assert open_accepted(store) == ([], [])


def test_rows_written_before_the_new_fields_still_read(tmp_path: Path) -> None:
    """A Decision or Ticket stored before it had a Mandate or a Trigger id reads back with none."""
    old_decision = '{"id": "m1@v", "trigger_id": "m1", "outcome": "accept", "reasons": ["x"]}'
    decision = codec.from_text(Decision, old_decision)
    assert decision.mandate is None
    old_ticket = '{"id": "t-1", "mandate": ' + codec.to_text(MANDATE) + ', "ended": false}'
    ticket = codec.from_text(Ticket, old_ticket)
    assert ticket.trigger_id is None
    with pytest.raises(KeyError):
        codec.from_text(Decision, '{"id": "m1@v", "outcome": "accept"}')


def test_the_task_has_the_policy_instructions_then_the_message() -> None:
    mandate = Mandate(
        policy_version=POLICY.version,
        strength=Strength.INFERRED,
        via=Via.ADMISSION,
        source="github",
        row="repo",
        sender="alice",
        rules=("ci-fix",),
    )
    task = task_for(POLICY, mandate, "CI is red")
    assert task.startswith("Standing instructions from the approved Policy:\nfix failing CI")
    assert task.index("fix failing CI") < task.index("CI is red")
    explicit = Mandate(
        policy_version=POLICY.version,
        strength=Strength.EXPLICIT,
        via=Via.ADDRESSED,
        source="github",
        row="repo",
        sender="alice",
    )
    only_message = task_for(POLICY, explicit, "please look")
    assert "Standing instructions" not in only_message
    assert "please look" in only_message


def test_a_run_moves_its_ticket_to_ready_for_a_person(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    store_with(path, message(1, "CI is red on the branch", addressed=Addressed.NONE))
    executor = FakeExecutor()
    report = drive(opener(path), executor)
    (ticket_id,) = report.opened
    assert report.ready == [ticket_id]
    assert report.failed == {}
    (ran_id, task) = executor.runs[0]
    assert ran_id == ticket_id
    assert "fix failing CI" in task
    assert "CI is red on the branch" in task
    with WorkStore(path) as store:
        ticket = store.ticket(ticket_id)
        assert ticket is not None
        assert stage_of(ticket) is Stage.PERSON_REVIEW
        assert ticket.assignment is not None
        assert ticket.assignment.state is AssignmentState.ENDED


def test_the_ticket_is_running_while_its_process_runs_and_no_store_is_held(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    store_with(path, message(1, "CI is red", addressed=Addressed.NONE))
    seen: list[object] = []

    def look(ticket_id: str) -> None:
        # A second writer can open the store during the run: the driver holds none.
        with WorkStore(path) as other:
            ticket = other.ticket(ticket_id)
            assert ticket is not None and ticket.assignment is not None
            seen.append(ticket.assignment.state)

    drive(opener(path), FakeExecutor(during=look))
    assert seen == [AssignmentState.RUNNING]


def test_a_stop_during_a_run_takes_effect_when_it_ends(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    store_with(path, message(1, "CI is red", addressed=Addressed.NONE))

    def stop_it(ticket_id: str) -> None:
        with WorkStore(path) as other:
            operator.stop(other, ticket_id)

    report = drive(opener(path), FakeExecutor(during=stop_it))
    (ticket_id,) = report.ready
    with WorkStore(path) as store:
        ticket = store.ticket(ticket_id)
        assert ticket is not None
        assert ticket.ended is True
        assert ticket.latest_report is not None
        assert store.open_tickets() == []


def test_a_failed_exit_waits_for_a_person(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    store_with(path, message(1, "CI is red", addressed=Addressed.NONE))
    failed = Execution("x", ok=False, exit_code=3)
    report = drive(opener(path), FakeExecutor([failed]))
    (ticket_id,) = report.opened
    assert report.failed == {ticket_id: "exit 3"}
    with WorkStore(path) as store:
        ticket = store.ticket(ticket_id)
        assert ticket is not None
        assert stage_of(ticket) is Stage.PERSON_BLOCKED
        assert operator.attention(store) == [
            {"kind": "ticket", "id": ticket_id, "detail": Stage.PERSON_BLOCKED.value}
        ]


@pytest.mark.parametrize(
    ("execution", "reason"),
    [
        (
            Execution("x", ok=False, refused="the program sudo is blocked"),
            "the program sudo is blocked",
        ),
        (Execution("x", ok=False, timed_out=True), "timed out"),
        (Execution("x", ok=False), "no exit code"),
    ],
)
def test_a_refused_or_timed_out_run_fails_with_its_reason(
    tmp_path: Path, execution: Execution, reason: str
) -> None:
    path = tmp_path / "work.sqlite"
    store_with(path, message(1, "CI is red", addressed=Addressed.NONE))
    report = drive(opener(path), FakeExecutor([execution]))
    (ticket_id,) = report.opened
    assert report.failed == {ticket_id: reason}


def test_no_free_slot_leaves_the_ticket_waiting_and_ends_the_pass(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    store_with(
        path,
        message(1, "CI is red", thread="github:issue-1", addressed=Addressed.NONE),
        message(2, "CI is red again", thread="github:issue-2", addressed=Addressed.NONE),
    )
    busy = Execution("x", ok=False, refused=SLOT_BUSY, busy=True)
    executor = FakeExecutor([busy])
    report = drive(opener(path), executor)
    first, second = report.opened
    assert report.waiting == [first]
    assert len(executor.runs) == 1
    assert ticket_state(path, first) == (AssignmentState.PENDING, None)
    assert ticket_state(path, second) == (AssignmentState.PENDING, None)


def test_an_executor_error_fails_only_that_ticket(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    store_with(
        path,
        message(1, "CI is red", thread="github:issue-1", addressed=Addressed.NONE),
        message(2, "CI is red again", thread="github:issue-2", addressed=Addressed.NONE),
    )
    report = drive(opener(path), ExplodingExecutor())
    first, second = report.opened
    assert report.failed == {first: "executor error: RuntimeError"}
    assert report.ready == [second]


def test_the_pass_runs_no_more_than_its_limit(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    store_with(
        path,
        *(
            message(n, "CI is red", thread=f"github:issue-{n}", addressed=Addressed.NONE)
            for n in range(1, 4)
        ),
    )
    report = drive(opener(path), FakeExecutor(), limit=2)
    assert len(report.ready) == 2
    third = ticket_id_for(next(d.id for d in _decisions(path) if d.trigger_id == "m3"))
    assert ticket_state(path, third) == (AssignmentState.PENDING, None)


def _decisions(path: Path) -> list[Decision]:
    with WorkStore(path) as store:
        return store.all_decisions()


def test_a_paused_store_opens_and_runs_nothing(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    store_with(path, message(1, "CI is red", addressed=Addressed.NONE))
    with WorkStore(path) as store:
        operator.pause(store)
    executor = FakeExecutor()
    paused = drive(opener(path), executor)
    assert paused == DriveReport(paused=True)
    assert executor.runs == []
    with WorkStore(path) as store:
        assert store.all_decisions() and store.open_tickets() == []
        operator.resume(store)
    assert drive(opener(path), executor).ready != []


def test_a_blocked_executor_changes_no_ticket(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    store_with(path, message(1, "CI is red", addressed=Addressed.NONE))
    executor = FakeExecutor(halt="containment needs Linux")
    report = drive(opener(path), executor)
    assert report.halted == "containment needs Linux"
    assert report.opened == []
    assert executor.runs == []
    with WorkStore(path) as store:
        assert store.open_tickets() == []


def test_the_executor_file_builds_the_executor(tmp_path: Path) -> None:
    config = tmp_path / "executor.json"
    config.write_text(
        json.dumps(
            {
                "root": str(tmp_path / "tickets"),
                "argv": ["claude", "-p", "{task}"],
                "prepare": ["git", "init"],
                "slots": 3,
            }
        ),
        encoding="utf-8",
    )
    executor = load_executor(config)
    assert isinstance(executor, ProcessExecutor)
    assert executor.argv == ["claude", "-p", "{task}"]
    assert executor.prepare == ["git", "init"]
    assert executor.slots.capacity == 3


@pytest.mark.parametrize(
    "settings",
    [
        {"argv": ["claude"]},
        {"root": "", "argv": ["claude"]},
        {"root": "r", "argv": []},
        {"root": "r", "argv": "claude"},
        {"root": "r", "argv": ["claude", 3]},
        {"root": "r", "argv": ["claude"], "prepare": "git"},
        {"root": "r", "argv": ["claude"], "slots": 1},
        {"root": "r", "argv": ["claude"], "slots": "2"},
        {"root": "r", "argv": ["claude"], "slots": True},
    ],
)
def test_an_executor_file_of_the_wrong_shape_is_refused(
    tmp_path: Path, settings: dict[str, Any]
) -> None:
    config = tmp_path / "executor.json"
    config.write_text(json.dumps(settings), encoding="utf-8")
    with pytest.raises(ValueError):
        load_executor(config)


def test_the_cli_drive_refuses_a_bad_executor_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "work.sqlite"
    config = tmp_path / "executor.json"
    config.write_text("[]", encoding="utf-8")
    assert cli.main(["work", "drive", "--store", str(path), "--executor", str(config)]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert cli.main(["work", "drive", "--store", str(path), "--executor", "nope.json"]) == 1


def test_the_cli_drive_reports_a_paused_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "work.sqlite"
    with WorkStore(path) as store:
        operator.pause(store)
    config = tmp_path / "executor.json"
    config.write_text(
        json.dumps({"root": str(tmp_path / "tickets"), "argv": ["claude", "{task}"]}),
        encoding="utf-8",
    )
    assert cli.main(["work", "drive", "--store", str(path), "--executor", str(config)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["paused"] is True


def fake_cli_settings(tmp_path: Path) -> Path:
    """An executor file whose CLI is a Python script. The script records its task, its working
    directory and which variables it was given, in result.json beside it."""
    fake_cli = tmp_path / "fake_cli.py"
    fake_cli.write_text(
        "import json, os, sys\n"
        "json.dump({\n"
        "    'task': sys.argv[1],\n"
        "    'key': 'ANTHROPIC_API_KEY' in os.environ,\n"
        "    'other': 'WORK_TEST_OTHER' in os.environ,\n"
        "}, open('result.json', 'w'))\n",
        encoding="utf-8",
    )
    config = tmp_path / "executor.json"
    config.write_text(
        json.dumps(
            {
                "root": str(tmp_path / "tickets"),
                "argv": [sys.executable, str(fake_cli), "{task}"],
            }
        ),
        encoding="utf-8",
    )
    return config


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the jail's containment is Linux")
def test_a_ticket_runs_in_the_real_jail_with_its_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setenv("WORK_TEST_OTHER", "must-not-pass")
    path = tmp_path / "work.sqlite"
    store_with(path, message(1, "CI is red on the branch", addressed=Addressed.NONE))
    report = drive(opener(path), load_executor(fake_cli_settings(tmp_path)))
    (ticket_id,) = report.ready
    written = json.loads((tmp_path / "tickets" / ticket_id / "result.json").read_text("utf-8"))
    assert "fix failing CI" in written["task"]
    assert "CI is red on the branch" in written["task"]
    assert written["key"] is True
    assert written["other"] is False


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the jail's containment is Linux")
def test_the_cli_drive_runs_the_queued_ticket_through_the_jail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    path = tmp_path / "work.sqlite"
    store_with(path, message(1, "CI is red", addressed=Addressed.NONE))
    config = fake_cli_settings(tmp_path)
    assert cli.main(["work", "drive", "--store", str(path), "--executor", str(config)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert len(out["opened"]) == 1
    assert out["ready"] == out["opened"]
    assert out["failed"] == {}
    assert cli.main(["work", "tickets", "--store", str(path)]) == 0
    (ticket,) = json.loads(capsys.readouterr().out)
    assert ticket["stage"] == Stage.PERSON_REVIEW.value
