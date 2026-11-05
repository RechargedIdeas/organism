"""The work agent's Executor: one coding-agent CLI run for one Ticket, inside the jail (v1.12 W5).
Design record: docs/v1.12/WORK_AGENT.md.

This runs processes, so it lives in this subpackage, beside `sources/` and `channels/`. A run goes:
refuse what must not run, take a worker slot, make the Ticket's directory, run the prepare argv if
there is one, then run the CLI argv in that directory under the `work_executor` profile. Every
refusal is a value in the Execution, so the caller can record it.

An Execution's stdout and stderr are output from a program the agent does not trust. A caller that
records them must treat them as data, never as instructions.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from organism_sdk.sandbox.jail import JailResult, ProcessJail, capabilities
from organism_sdk.sandbox.policy import SandboxPolicy
from organism_sdk.work.domain import AssignmentState
from organism_sdk.work.store import WorkStore

# Programs that open a shell, a remote host or a privilege. The CLI itself is not on this list.
BLOCKED_PROGRAMS = frozenset({"sudo", "su", "doas", "ssh", "scp", "sftp", "nc", "netcat", "telnet"})
PREPARE_TIMEOUT_S = 600.0
PERSON_RESERVE = 1  # D4: one worker slot stays free for a person's message
TICKET_DIRECTORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
RECOVERY = "recovery"
SLOT_BUSY = "no worker slot is free"
# An argv element equal to this is replaced by the Ticket's task. No shell expands it.
TASK_PLACEHOLDER = "{task}"


@dataclass(frozen=True)
class Execution:
    """What one run did. `refused` is set when nothing ran; the other fields then stay empty.

    `busy` is True when the only reason nothing ran is that no worker slot was free. The Ticket
    can then run later, so it is not a failure.
    """

    ticket_id: str
    ok: bool
    refused: str | None = None
    exit_code: int | None = None
    timed_out: bool = False
    workdir: str | None = None
    stdout: str = ""
    stderr: str = ""
    busy: bool = False


class Executor(Protocol):
    def blocked_reason(self) -> str | None:
        """Why nothing can run on this host or in this configuration, or None when runs can start."""
        ...

    def run(self, ticket_id: str, *, person: bool = False, task: str = "") -> Execution: ...


class Runner(Protocol):
    """Runs one argv under a policy. `ProcessJail` is the real one; tests substitute another."""

    def run(
        self,
        argv: Sequence[str],
        *,
        env: dict[str, str] | None = None,
        input_bytes: bytes | None = None,
        cwd: str | None = None,
    ) -> JailResult: ...


class Slots:
    """Worker slots (D4). Ticket work may use every slot but `reserve`, so a person always has one."""

    def __init__(self, capacity: int, *, reserve: int = PERSON_RESERVE) -> None:
        if capacity < 1 or not 0 <= reserve < capacity:
            raise ValueError("capacity must be at least one, and above the reserve")
        self.capacity = capacity
        self.reserve = reserve
        self._free = capacity
        self._cond = threading.Condition()

    @property
    def free(self) -> int:
        with self._cond:
            return self._free

    def acquire(self, *, person: bool, timeout: float) -> bool:
        floor = 0 if person else self.reserve
        with self._cond:
            if not self._cond.wait_for(lambda: self._free > floor, timeout=timeout):
                return False
            self._free -= 1
            return True

    def release(self) -> None:
        with self._cond:
            self._free += 1
            self._cond.notify()


def containment_gap(caps: dict[str, Any] | None = None) -> str | None:
    """Why this host cannot contain the executor's child, or None when it can.

    Rlimits and namespaces are both needed. Windows has neither, so the executor is refused there.
    """
    found = capabilities() if caps is None else caps
    if not found["linux"]:
        return "containment needs Linux, so this host cannot run the executor"
    if not found["rlimits"]:
        return "rlimits are unavailable, so this host cannot run the executor"
    if not found["unshare"]:
        return "namespaces are unavailable, so this host cannot run the executor"
    return None


def _program_name(argv0: str) -> str:
    """The program's bare name, lowercase and without `.exe`, for either path separator."""
    name = re.split(r"[\\/]", argv0)[-1].lower()
    return name.removesuffix(".exe")


def ticket_directory(root: Path, ticket_id: str) -> Path:
    """The Ticket's own directory under `root`. Raises ValueError for an id that is not a safe name."""
    if not TICKET_DIRECTORY.fullmatch(ticket_id):
        raise ValueError(f"ticket id {ticket_id!r} is not a safe directory name")
    return root / ticket_id


class ProcessExecutor:
    """Runs the configured CLI argv for a Ticket, in the Ticket's own directory."""

    def __init__(
        self,
        root: Path,
        *,
        argv: Sequence[str],
        slots: Slots,
        prepare: Sequence[str] | None = None,
        policy: SandboxPolicy | None = None,
        jail: Callable[[SandboxPolicy], Runner] = ProcessJail,
        containment_check: Callable[[], str | None] = containment_gap,
        slot_wait_s: float = 5.0,
    ) -> None:
        if not argv:
            raise ValueError("the executor needs an argv")
        self.root = Path(root)
        self.argv = [str(a) for a in argv]
        self.prepare = None if prepare is None else [str(a) for a in prepare]
        self.slots = slots
        self.policy = SandboxPolicy.work_executor() if policy is None else policy
        self.prepare_policy = replace(self.policy, timeout_s=PREPARE_TIMEOUT_S)
        self.jail = jail
        self.containment_check = containment_check
        self.slot_wait_s = slot_wait_s

    def blocked_reason(self) -> str | None:
        return self._refusal()

    def run(self, ticket_id: str, *, person: bool = False, task: str = "") -> Execution:
        refusal = self._refusal()
        if refusal is not None:
            return Execution(ticket_id, ok=False, refused=refusal)
        try:
            directory = ticket_directory(self.root, ticket_id)
        except ValueError as error:
            return Execution(ticket_id, ok=False, refused=str(error))
        if not self.slots.acquire(person=person, timeout=self.slot_wait_s):
            return Execution(ticket_id, ok=False, refused=SLOT_BUSY, busy=True)
        try:
            return self._run_in_directory(ticket_id, directory, task)
        finally:
            self.slots.release()

    def _refusal(self) -> str | None:
        program = _program_name(self.argv[0])
        if program in BLOCKED_PROGRAMS:
            return f"the program {program} is blocked for the executor"
        gap = self.containment_check()
        if gap is not None:
            return gap
        names = self.policy.env_allowlist or ()
        # Names the variables only. The value is never read here, so it cannot reach a message.
        if names and not any(name in os.environ for name in names):
            return "none of the variables the profile passes is set: " + ", ".join(names)
        return None

    def _run_in_directory(self, ticket_id: str, directory: Path, task: str) -> Execution:
        directory.mkdir(parents=True, exist_ok=True)
        where = str(directory)
        if self.prepare is not None:
            step = self.jail(self.prepare_policy).run(self.prepare, cwd=where)
            if not step.ok:
                return _from_jail(ticket_id, step, where)
        argv = [task if item == TASK_PLACEHOLDER else item for item in self.argv]
        result = self.jail(self.policy).run(argv, cwd=where)
        return _from_jail(ticket_id, result, where)


def _from_jail(ticket_id: str, result: Any, where: str) -> Execution:
    return Execution(
        ticket_id,
        ok=result.ok,
        refused=result.refused,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
        workdir=where,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def recover(store: WorkStore) -> list[str]:
    """After a restart, end every running Assignment and queue a recovery note for its Ticket.

    The note waits in the effects queue, where `attention` shows it. Nothing reruns here: a retry
    starts a new Assignment in the same directory (D2). Returns the Tickets that were noted.
    """
    noted: list[str] = []
    with store.transaction():
        for ticket in store.open_tickets():
            for assignment in store.assignments_of(ticket.id):
                if assignment.state is not AssignmentState.RUNNING:
                    continue
                store.save_assignment(replace(assignment, state=AssignmentState.ENDED))
                store.enqueue(RECOVERY, ticket.id, {"assignment": assignment.id})
                if ticket.id not in noted:
                    noted.append(ticket.id)
    return noted
