"""The work store: durable state of the work agent (v1.12). Design record: docs/v1.12/WORK_AGENT.md.

This is the only top-level module of the work package that does I/O. The adapters in `sources/` do too. It keeps state in SQLite in WAL
mode, as the workspace ops log does (`organism_sdk.snapshot`). Opening a store takes a writer
lock on its `.lock` file. A second writer, in this process or another, is refused at once with
`StoreInUse`, and the OS drops the lock when a process dies, so a crash leaves nothing to clear.
An in-process lock serializes threads. WAL lets readers run beside the writer.

A round of intake is one transaction. Its Triggers, the Source's cursor and the effects it
queues commit together or not at all, so a restart neither drops nor repeats a Trigger.

Effects run at least once. A handler that finishes but is killed before its completion is
stored runs again after the restart, so every handler must be idempotent.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Self

from organism_sdk.work import codec
from organism_sdk.work.domain import Assignment, Decision, Ticket, Trigger, Verdict

SCHEMA_VERSION = "2"
BACKOFF_BASE_S = 5.0
BACKOFF_CAP_S = 300.0
ERROR_CHARS = 500

SCHEMA = """
CREATE TABLE IF NOT EXISTS flags (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS triggers (
  id TEXT PRIMARY KEY,
  thread TEXT NOT NULL,
  at TEXT NOT NULL,
  received REAL NOT NULL,
  body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS triggers_thread ON triggers (thread, at, id);
CREATE TABLE IF NOT EXISTS cursors (source TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions (
  id TEXT PRIMARY KEY,
  trigger_id TEXT NOT NULL,
  body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS decisions_trigger ON decisions (trigger_id);
CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY,
  thread TEXT,
  ended INTEGER NOT NULL,
  body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tickets_thread ON tickets (thread, ended);
CREATE TABLE IF NOT EXISTS labels (
  decision_id TEXT PRIMARY KEY,
  verdict TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assignments (
  id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS assignments_ticket ON assignments (ticket_id);
CREATE TABLE IF NOT EXISTS effects (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  key TEXT NOT NULL,
  payload TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  due_at REAL NOT NULL,
  last_error TEXT,
  UNIQUE (kind, key)
);
CREATE TABLE IF NOT EXISTS receipts (
  id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL,
  conversation TEXT NOT NULL,
  text TEXT NOT NULL,
  status TEXT NOT NULL,
  reason TEXT
);
CREATE TABLE IF NOT EXISTS source_errors (
  source TEXT NOT NULL,
  item TEXT NOT NULL,
  message TEXT NOT NULL,
  PRIMARY KEY (source, item)
);
"""


class ReceiptStatus(str, Enum):
    """Where an outbound message is. A message is never queued twice."""

    PENDING = "pending"
    SENT = "sent"
    DROPPED = "dropped"


@dataclass(frozen=True)
class Effect:
    """A piece of stored work waiting to run, such as a reply to send."""

    seq: int
    kind: str
    key: str
    payload: Mapping[str, Any]
    attempts: int
    due_at: float
    last_error: str | None


@dataclass(frozen=True)
class Receipt:
    """An outbound message and what became of it."""

    id: str
    ticket_id: str
    conversation: str
    text: str
    status: ReceiptStatus
    reason: str | None


@dataclass(frozen=True)
class RunReport:
    """How many due effects completed and how many failed in one run."""

    completed: int
    failed: int


class StoreInUse(RuntimeError):
    """Another WorkStore holds this store's writer lock, in this process or another."""


def _take_writer_lock(path: Path) -> int:
    """Take the writer lock on the store's `.lock` file. Refuses at once if it is held."""
    fd = os.open(path.with_name(f"{path.name}.lock"), os.O_RDWR | os.O_CREAT)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise StoreInUse(f"work store {path} is in use by another writer") from None
    return fd


def _release_writer_lock(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    os.close(fd)  # on POSIX, closing the descriptor drops the flock


def _open_database(path: Path) -> sqlite3.Connection:
    """Open the database in WAL mode with full sync, and check its schema version."""
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.executescript(SCHEMA)
        row = conn.execute("SELECT value FROM flags WHERE name = 'schema'").fetchone()
        if row is None:
            conn.execute("INSERT INTO flags (name, value) VALUES ('schema', ?)", (SCHEMA_VERSION,))
        elif row[0] != SCHEMA_VERSION:
            raise RuntimeError(f"work store schema {row[0]} is not {SCHEMA_VERSION}")
    except BaseException:
        conn.close()
        raise
    return conn


def backoff_seconds(attempts: int) -> float:
    """The wait after the given number of failures: 5, 10, 20 ... seconds, capped at 300."""
    if attempts < 1:
        raise ValueError("a backoff follows at least one failure")
    return min(BACKOFF_BASE_S * 2.0 ** (attempts - 1), BACKOFF_CAP_S)


class WorkStore:
    """SQLite state of the work agent. Open one per state directory."""

    def __init__(self, path: Path | str, *, clock: Callable[[], float] = time.time) -> None:
        self.path = Path(path)
        self._clock = clock
        self._lock = threading.RLock()
        self._depth = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = _take_writer_lock(self.path)
        try:
            self._conn = _open_database(self.path)
        except BaseException:
            _release_writer_lock(fd)
            raise
        self._writer_fd: int | None = fd

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the store and release its writer lock. Closing twice does nothing."""
        with self._lock:
            if self._writer_fd is None:
                return
            self._conn.close()
            _release_writer_lock(self._writer_fd)
            self._writer_fd = None

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group writes into one transaction. A nested call joins the outer transaction."""
        with self._lock:
            if self._depth > 0:
                self._depth += 1
                try:
                    yield
                finally:
                    self._depth -= 1
                return
            self._conn.execute("BEGIN IMMEDIATE")
            self._depth = 1
            try:
                yield
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            finally:
                self._depth = 0

    # Intake

    def receive(self, trigger: Trigger) -> bool:
        """Store a Trigger once. True when it was new, False when its id was already stored."""
        with self.transaction():
            return self._insert_trigger(trigger)

    def commit_round(
        self,
        source: str,
        triggers: Iterable[Trigger],
        *,
        cursor: str,
        effects: Iterable[tuple[str, str, Mapping[str, Any]]] = (),
    ) -> int:
        """Store one round of intake atomically: its Triggers, the Source's cursor, its effects.

        Returns how many of the Triggers were new.
        """
        with self.transaction():
            new = 0
            for trigger in triggers:
                if self._insert_trigger(trigger):
                    new += 1
            self._set_cursor(source, cursor)
            for kind, key, payload in effects:
                self._enqueue(kind, key, payload)
            return new

    def cursor(self, source: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM cursors WHERE source = ?", (source,)
            ).fetchone()
        return None if row is None else str(row[0])

    def trigger(self, trigger_id: str) -> Trigger | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT body FROM triggers WHERE id = ?", (trigger_id,)
            ).fetchone()
        return None if row is None else codec.from_text(Trigger, row[0])

    def triggers_in_thread(self, thread: str) -> list[Trigger]:
        """The Triggers of one Thread, in time order and then by id."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT body FROM triggers WHERE thread = ? ORDER BY at, id", (thread,)
            ).fetchall()
        return [codec.from_text(Trigger, row[0]) for row in rows]

    def trigger_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM triggers").fetchone()
        return int(row[0])

    def _insert_trigger(self, trigger: Trigger) -> bool:
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO triggers (id, thread, at, received, body) VALUES (?, ?, ?, ?, ?)",
            (trigger.id, trigger.thread, trigger.at, self._clock(), codec.to_text(trigger)),
        )
        return cursor.rowcount == 1

    def _set_cursor(self, source: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO cursors (source, value) VALUES (?, ?) "
            "ON CONFLICT (source) DO UPDATE SET value = excluded.value",
            (source, value),
        )

    # Decisions, Tickets and Assignments

    def save_decision(self, decision: Decision) -> bool:
        """Store a Decision. True when it was new; a Decision is never replaced."""
        with self.transaction():
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO decisions (id, trigger_id, body) VALUES (?, ?, ?)",
                (decision.id, decision.trigger_id, codec.to_text(decision)),
            )
        return cursor.rowcount == 1

    def decisions_for(self, trigger_id: str) -> list[Decision]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT body FROM decisions WHERE trigger_id = ? ORDER BY rowid", (trigger_id,)
            ).fetchall()
        return [codec.from_text(Decision, row[0]) for row in rows]

    def save_ticket(self, ticket: Ticket) -> None:
        """Store a Ticket, replacing the stored facts of the same id."""
        with self.transaction():
            self._conn.execute(
                "INSERT INTO tickets (id, thread, ended, body) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (id) DO UPDATE SET thread = excluded.thread, "
                "ended = excluded.ended, body = excluded.body",
                (ticket.id, ticket.thread, int(ticket.ended), codec.to_text(ticket)),
            )

    def ticket(self, ticket_id: str) -> Ticket | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT body FROM tickets WHERE id = ?", (ticket_id,)
            ).fetchone()
        return None if row is None else codec.from_text(Ticket, row[0])

    def open_tickets(self) -> list[Ticket]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT body FROM tickets WHERE ended = 0 ORDER BY rowid"
            ).fetchall()
        return [codec.from_text(Ticket, row[0]) for row in rows]

    def save_assignment(self, assignment: Assignment) -> None:
        with self.transaction():
            self._conn.execute(
                "INSERT INTO assignments (id, ticket_id, body) VALUES (?, ?, ?) "
                "ON CONFLICT (id) DO UPDATE SET body = excluded.body",
                (assignment.id, assignment.ticket_id, codec.to_text(assignment)),
            )

    def assignments_of(self, ticket_id: str) -> list[Assignment]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT body FROM assignments WHERE ticket_id = ? ORDER BY rowid", (ticket_id,)
            ).fetchall()
        return [codec.from_text(Assignment, row[0]) for row in rows]

    # Outbound receipts

    def add_receipt(self, receipt_id: str, *, ticket_id: str, conversation: str, text: str) -> bool:
        """Queue an outbound message once. True when it was new; a repeat changes nothing."""
        with self.transaction():
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO receipts (id, ticket_id, conversation, text, status, reason) "
                "VALUES (?, ?, ?, ?, ?, NULL)",
                (receipt_id, ticket_id, conversation, text, ReceiptStatus.PENDING.value),
            )
        return cursor.rowcount == 1

    def settle_receipt(
        self, receipt_id: str, status: ReceiptStatus, reason: str | None = None
    ) -> None:
        """Record that a message was sent or dropped. An unknown id raises KeyError."""
        with self.transaction():
            cursor = self._conn.execute(
                "UPDATE receipts SET status = ?, reason = ? WHERE id = ?",
                (status.value, reason, receipt_id),
            )
        if cursor.rowcount != 1:
            raise KeyError(receipt_id)

    def receipt(self, receipt_id: str) -> Receipt | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, ticket_id, conversation, text, status, reason FROM receipts "
                "WHERE id = ?",
                (receipt_id,),
            ).fetchone()
        if row is None:
            return None
        return Receipt(
            id=row[0],
            ticket_id=row[1],
            conversation=row[2],
            text=row[3],
            status=ReceiptStatus(row[4]),
            reason=row[5],
        )

    # Source outcomes

    def record_source_outcomes(
        self, source: str, *, failed: Mapping[str, str], succeeded: Iterable[str]
    ) -> None:
        """Keep each failed item's own error, and clear the error of each item that succeeded.

        A caller inside `transaction()` makes these writes part of its round.
        """
        with self.transaction():
            for item in succeeded:
                self._conn.execute(
                    "DELETE FROM source_errors WHERE source = ? AND item = ?", (source, item)
                )
            for item, message in failed.items():
                self._conn.execute(
                    "INSERT INTO source_errors (source, item, message) VALUES (?, ?, ?) "
                    "ON CONFLICT (source, item) DO UPDATE SET message = excluded.message",
                    (source, item, message[:ERROR_CHARS]),
                )

    def source_errors(self, source: str) -> dict[str, str]:
        """The errors of the items of one Source that have not succeeded since they failed."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT item, message FROM source_errors WHERE source = ? ORDER BY item", (source,)
            ).fetchall()
        return {str(item): str(message) for item, message in rows}

    # Evaluation

    def now(self) -> float:
        """The store's clock. Eval measures deadlines against it."""
        return self._clock()

    def undecided(self, policy_version: str) -> list[tuple[Trigger, float]]:
        """The Triggers with no Decision under this Policy version, each with its receipt time.

        The Decision's key is the Trigger id, "@", then the version (see `decision_key`). Oldest
        first, so a backlog is worked in the order it arrived.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT body, received FROM triggers WHERE NOT EXISTS ("
                "SELECT 1 FROM decisions WHERE decisions.id = triggers.id || '@' || ?) "
                "ORDER BY received, id",
                (policy_version,),
            ).fetchall()
        return [(codec.from_text(Trigger, body), float(received)) for body, received in rows]

    def ticket_for_thread(self, thread: str) -> Ticket | None:
        """The newest open Ticket of a Thread, or None when the Thread has none."""
        with self._lock:
            row = self._conn.execute(
                "SELECT body FROM tickets WHERE thread = ? AND ended = 0 "
                "ORDER BY rowid DESC LIMIT 1",
                (thread,),
            ).fetchone()
        return None if row is None else codec.from_text(Ticket, row[0])

    def all_decisions(self) -> list[Decision]:
        with self._lock:
            rows = self._conn.execute("SELECT body FROM decisions ORDER BY rowid").fetchall()
        return [codec.from_text(Decision, row[0]) for row in rows]

    def label(self, decision_id: str, verdict: Verdict) -> None:
        """Record a person's verdict on a Decision. The latest verdict stands.

        An unknown Decision raises KeyError.
        """
        with self.transaction():
            known = self._conn.execute(
                "SELECT 1 FROM decisions WHERE id = ?", (decision_id,)
            ).fetchone()
            if known is None:
                raise KeyError(decision_id)
            self._conn.execute(
                "INSERT INTO labels (decision_id, verdict) VALUES (?, ?) "
                "ON CONFLICT (decision_id) DO UPDATE SET verdict = excluded.verdict",
                (decision_id, verdict.value),
            )

    def labels(self) -> dict[str, Verdict]:
        with self._lock:
            rows = self._conn.execute("SELECT decision_id, verdict FROM labels").fetchall()
        return {str(decision_id): Verdict(verdict) for decision_id, verdict in rows}

    # Effects

    def enqueue(self, kind: str, key: str, payload: Mapping[str, Any]) -> None:
        """Queue an effect. A waiting effect with the same kind and key takes the new payload,
        becomes due at once, and keeps its place in the queue."""
        with self.transaction():
            self._enqueue(kind, key, payload)

    def _enqueue(self, kind: str, key: str, payload: Mapping[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO effects (kind, key, payload, due_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (kind, key) DO UPDATE SET "
            "payload = excluded.payload, due_at = excluded.due_at",
            (kind, key, codec.to_text(dict(payload)), self._clock()),
        )

    def pending_effects(self) -> list[Effect]:
        """Every queued effect, in queue order, due or not."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, kind, key, payload, attempts, due_at, last_error "
                "FROM effects ORDER BY seq"
            ).fetchall()
        return [_effect(row) for row in rows]

    def run_due(
        self,
        handlers: Mapping[str, Callable[[Mapping[str, Any]], None]],
        *,
        limit: int = 50,
    ) -> RunReport:
        """Run the due effects of the kinds that have a handler, oldest first, up to `limit`.

        Nothing runs while the store is paused. An effect whose handler raises is counted as
        failed and waits `backoff_seconds` before it is tried again. An effect of a kind
        without a handler is left alone. An effect that is due when the run starts runs at
        most once in that run.
        """
        if self.paused:
            return RunReport(completed=0, failed=0)
        completed = 0
        failed = 0
        for effect in self._due(handlers)[:limit]:
            try:
                handlers[effect.kind](effect.payload)
            except Exception as error:  # noqa: BLE001 - a failing effect must not stop the queue
                self._fail(effect, error)
                failed += 1
            else:
                self._complete(effect)
                completed += 1
        return RunReport(completed=completed, failed=failed)

    def _due(self, handlers: Mapping[str, Callable[[Mapping[str, Any]], None]]) -> list[Effect]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, kind, key, payload, attempts, due_at, last_error "
                "FROM effects WHERE due_at <= ? ORDER BY seq",
                (self._clock(),),
            ).fetchall()
        return [_effect(row) for row in rows if row[1] in handlers]

    def _complete(self, effect: Effect) -> None:
        # Delete only if the payload is unchanged. A handler that queued the same effect again
        # leaves the new payload in place, to run on the next pass.
        with self.transaction():
            self._conn.execute(
                "DELETE FROM effects WHERE seq = ? AND payload = ?",
                (effect.seq, codec.to_text(dict(effect.payload))),
            )

    def _fail(self, effect: Effect, error: Exception) -> None:
        attempts = effect.attempts + 1
        due_at = self._clock() + backoff_seconds(attempts)
        message = f"{type(error).__name__}: {error}"[:ERROR_CHARS]
        with self.transaction():
            self._conn.execute(
                "UPDATE effects SET attempts = ?, due_at = ?, last_error = ? WHERE seq = ?",
                (attempts, due_at, message, effect.seq),
            )

    # Processing

    @property
    def paused(self) -> bool:
        """True while processing is paused. Intake keeps recording; nothing runs."""
        with self._lock:
            row = self._conn.execute("SELECT value FROM flags WHERE name = 'paused'").fetchone()
        return row is not None and row[0] == "1"

    def set_paused(self, paused: bool) -> None:
        with self.transaction():
            self._conn.execute(
                "INSERT INTO flags (name, value) VALUES ('paused', ?) "
                "ON CONFLICT (name) DO UPDATE SET value = excluded.value",
                ("1" if paused else "0",),
            )


def _effect(row: tuple[Any, ...]) -> Effect:
    seq, kind, key, payload, attempts, due_at, last_error = row
    return Effect(
        seq=int(seq),
        kind=str(kind),
        key=str(key),
        payload=_json_object(payload),
        attempts=int(attempts),
        due_at=float(due_at),
        last_error=None if last_error is None else str(last_error),
    )


def _json_object(text: str) -> dict[str, Any]:
    value = codec.from_text(dict, text)
    if not isinstance(value, dict):
        raise TypeError("an effect payload is a JSON object")
    return value
