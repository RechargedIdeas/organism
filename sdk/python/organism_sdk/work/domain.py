"""Work agent domain types (v1.12). Design record: docs/v1.12/WORK_AGENT.md.

Plain, immutable values. Nothing here performs I/O, so every rule built on these types
can be tested without a store, a network or a clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Addressed(str, Enum):
    """How a message addresses the agent. The Source records it; the gate reads it."""

    NONE = "none"
    MENTION = "mention"
    DIRECT = "direct"


class Strength(str, Enum):
    """How strong the basis of a Mandate or an Eval is."""

    EXPLICIT = "explicit"
    INFERRED = "inferred"
    NOT_ADMITTED = "not_admitted"


class Via(str, Enum):
    """The basis on which the gate admitted a Trigger."""

    ADDRESSED = "addressed"
    FOLLOWUP = "followup"
    ADMISSION = "admission"
    BOT = "bot"


class Outcome(str, Enum):
    """The result of Eval for one Trigger."""

    ACCEPT = "accept"
    STOP = "stop"
    IGNORE = "ignore"
    UNAVAILABLE = "unavailable"


class Verdict(str, Enum):
    """A person's judgment of a Decision: would starting the work have been right? (W4)"""

    AGREE = "agree"
    DISAGREE = "disagree"


class Report(str, Enum):
    """What an Executor reports to its Ticket."""

    PROGRESS = "progress"
    WAITING = "waiting"
    READY = "ready"
    BLOCKED = "blocked"
    FAILED = "failed"
    DROPPED = "dropped"


class AssignmentState(str, Enum):
    """Where an Assignment is in its life, independently of its Ticket."""

    PENDING = "pending"
    RUNNING = "running"
    ENDED = "ended"


def thread_key(source: str, native_id: str) -> str:
    """The key of a Thread: its Source, then the Source's own id."""
    return f"{source}:{native_id}"


def decision_key(trigger_id: str, policy_version: str) -> str:
    """The key of a Decision: its Trigger, then "@", then the Policy version it was made under."""
    return f"{trigger_id}@{policy_version}"


@dataclass(frozen=True)
class Trigger:
    """One immutable event from a Source (001).

    ``actor`` is None for an event with no sender, such as a CI result. ``thread`` is the
    key of the one Thread the Trigger belongs to; several Threads per Trigger wait for W2.
    """

    id: str
    source: str
    thread: str
    actor: str | None
    human: bool
    addressed: Addressed
    at: str
    text: str


@dataclass(frozen=True)
class Thread:
    """Triggers in time order, keyed by Source (001)."""

    key: str
    source: str


@dataclass(frozen=True)
class Mandate:
    """What an accept grants (001). Immutable: a wider scope needs a new Ticket."""

    policy_version: str
    strength: Strength
    via: Via
    source: str
    row: str | None
    sender: str | None
    rules: tuple[str, ...] = ()


@dataclass(frozen=True)
class Assignment:
    """The binding of a Ticket to one Executor instance (001)."""

    id: str
    ticket_id: str
    state: AssignmentState


@dataclass(frozen=True)
class Ticket:
    """A unit of authorized work (001, 003).

    The fields are the facts the stage table reads. The store (W2) keeps them current.
    ``latest_report`` is None until the Executor reports. ``person_message_after_report``
    is True when a person has written to the Ticket since that report. ``trigger_id`` is the
    Trigger the Ticket opened from, so the driver can give the Executor its task.
    """

    id: str
    mandate: Mandate
    ended: bool = False
    assignment: Assignment | None = None
    latest_report: Report | None = None
    attention: bool = False
    delivery_failed: bool = False
    person_message_after_report: bool = False
    thread: str | None = None
    trigger_id: str | None = None


@dataclass(frozen=True)
class Decision:
    """The result of Eval for one Trigger (001). ``reasons`` are codes, not prose.

    ``mandate`` is set only when the outcome is ACCEPT: it is the Mandate the Ticket opens with.
    """

    id: str
    trigger_id: str
    outcome: Outcome
    reasons: tuple[str, ...] = ()
    mandate: Mandate | None = None
