"""v1.12 work store across a crash: a process killed mid-round or mid-effect restarts cleanly.

Each crash runs in a child process that ends with os._exit. That skips Python's cleanup and
leaves the database as SQLite left it, as a power cut or a kill would. The parent then reopens
the store and checks what survived and what the replay does.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from organism_sdk.work.domain import Addressed, Trigger
from organism_sdk.work.store import RunReport, WorkStore

SDK = Path(__file__).resolve().parents[1]
CRASH = 17
REFUSED = 3

# The child receives the database path, the scenario and the sink file as arguments.
CHILD = """
import os
import sys

from organism_sdk.work.domain import Addressed, Trigger
from organism_sdk.work.store import StoreInUse, WorkStore


def trigger(n):
    return Trigger(
        id=f"m{n}",
        source="github",
        thread="github:issue-1",
        actor="alice",
        human=True,
        addressed=Addressed.MENTION,
        at=f"2026-11-04T00:00:{n:02d}Z",
        text=f"message {n}",
    )


def round_of_two(store):
    store.commit_round(
        "github",
        [trigger(1), trigger(2)],
        cursor="c2",
        effects=[("reply", "m1", {"text": "on it"})],
    )


path, scenario, sink = sys.argv[1:4]
if scenario == "held":
    try:
        WorkStore(path)
    except StoreInUse:
        os._exit(3)
    os._exit(0)
store = WorkStore(path)
if scenario == "before-commit":
    with store.transaction():
        round_of_two(store)
        os._exit(17)
if scenario == "after-commit":
    round_of_two(store)
    os._exit(17)
if scenario == "in-effect":

    def send(payload):
        with open(sink, "a", encoding="utf-8") as file:
            file.write(payload["text"] + "\\n")
        os._exit(17)

    store.enqueue("reply", "m1", {"text": "on it"})
    store.run_due({"reply": send})
if scenario == "paused":
    store.set_paused(True)
    os._exit(17)
"""


def trigger(n: int) -> Trigger:
    return Trigger(
        id=f"m{n}",
        source="github",
        thread="github:issue-1",
        actor="alice",
        human=True,
        addressed=Addressed.MENTION,
        at=f"2026-11-04T00:00:{n:02d}Z",
        text=f"message {n}",
    )


def run_child(db: Path, scenario: str, sink: Path) -> subprocess.CompletedProcess[str]:
    """Run one child process of the scenario and return how it ended."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SDK), env.get("PYTHONPATH", "")) if part
    )
    return subprocess.run(
        [sys.executable, "-c", CHILD, str(db), scenario, str(sink)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def crash(db: Path, scenario: str, sink: Path) -> None:
    """Run a child that dies at the named point, and check that it died there."""
    done = run_child(db, scenario, sink)
    assert done.returncode == CRASH, done.stderr


def send_to(sink: Path) -> Callable[[Mapping[str, Any]], None]:
    """A send that records each message in the sink file, as the child's does."""

    def send(payload: Mapping[str, Any]) -> None:
        with sink.open("a", encoding="utf-8") as file:
            file.write(f"{payload['text']}\n")

    return send


def test_a_round_killed_before_its_commit_leaves_nothing_and_its_replay_stores_it_once(
    tmp_path: Path,
) -> None:
    db = tmp_path / "work.sqlite"
    crash(db, "before-commit", tmp_path / "sink.txt")
    with WorkStore(db) as store:
        assert store.trigger_count() == 0
        assert store.cursor("github") is None
        assert store.pending_effects() == []

        new = store.commit_round(
            "github",
            [trigger(1), trigger(2)],
            cursor="c2",
            effects=[("reply", "m1", {"text": "on it"})],
        )
        assert new == 2
        assert store.trigger_count() == 2
        assert store.cursor("github") == "c2"
        assert len(store.pending_effects()) == 1


def test_a_round_committed_before_a_crash_is_kept_and_its_replay_adds_nothing(
    tmp_path: Path,
) -> None:
    db = tmp_path / "work.sqlite"
    crash(db, "after-commit", tmp_path / "sink.txt")
    with WorkStore(db) as store:
        assert store.trigger_count() == 2
        assert store.cursor("github") == "c2"
        assert [effect.key for effect in store.pending_effects()] == ["m1"]

        new = store.commit_round(
            "github",
            [trigger(1), trigger(2)],
            cursor="c2",
            effects=[("reply", "m1", {"text": "on it"})],
        )
        assert new == 0
        assert store.trigger_count() == 2
        assert len(store.pending_effects()) == 1


def test_an_effect_killed_mid_run_runs_again_and_leaves_the_queue(tmp_path: Path) -> None:
    db = tmp_path / "work.sqlite"
    sink = tmp_path / "sink.txt"
    crash(db, "in-effect", sink)
    assert sink.read_text(encoding="utf-8").splitlines() == ["on it"]

    with WorkStore(db) as store:
        assert [(effect.key, effect.attempts) for effect in store.pending_effects()] == [("m1", 0)]
        assert store.run_due({"reply": send_to(sink)}) == RunReport(completed=1, failed=0)
        assert store.pending_effects() == []

    # The send ran twice. The crash came after the send and before its completion was stored,
    # so the replay repeats it. This is why every effect handler must be idempotent.
    assert sink.read_text(encoding="utf-8").splitlines() == ["on it", "on it"]


def test_the_paused_flag_survives_a_crash_and_nothing_runs_while_it_is_set(
    tmp_path: Path,
) -> None:
    db = tmp_path / "work.sqlite"
    sink = tmp_path / "sink.txt"
    crash(db, "paused", sink)

    with WorkStore(db) as store:
        assert store.paused is True
        store.enqueue("reply", "m1", {"text": "hi"})
        assert store.run_due({"reply": send_to(sink)}) == RunReport(completed=0, failed=0)
        assert not sink.exists()

        store.set_paused(False)
        assert store.run_due({"reply": send_to(sink)}) == RunReport(completed=1, failed=0)
    assert sink.read_text(encoding="utf-8").splitlines() == ["hi"]


def test_a_crashed_writer_releases_the_lock_for_the_next_process(tmp_path: Path) -> None:
    db = tmp_path / "work.sqlite"
    crash(db, "paused", tmp_path / "sink.txt")
    WorkStore(db).close()


def test_a_child_process_is_refused_while_another_holds_the_store(tmp_path: Path) -> None:
    db = tmp_path / "work.sqlite"
    with WorkStore(db):
        done = run_child(db, "held", tmp_path / "sink.txt")
    assert done.returncode == REFUSED, done.stderr
