"""The operator's view of the work agent (v1.12 W7). Design record: docs/v1.12/WORK_AGENT.md.

The CLI (`organism work`) and the desktop `needs_you` panel both call these functions, so they show
the same state and make the same changes. Reads need only a read-only store, which runs beside the
writer. Changes take the writer lock, and are refused while another writer holds it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any

from organism_sdk.signing import TrustStore
from organism_sdk.work import governance
from organism_sdk.work.assess import RuleAssessor
from organism_sdk.work.channels.replies import REPLY
from organism_sdk.work.domain import AssignmentState, Verdict
from organism_sdk.work.driver import requeue
from organism_sdk.work.executors.process import RECOVERY
from organism_sdk.work.gate import ScopeFacts
from organism_sdk.work.governance import NOTICE
from organism_sdk.work.policy import Policy
from organism_sdk.work.runner import EvalReport, Listens, evaluate
from organism_sdk.work.stage import Stage, stage_of
from organism_sdk.work.store import ReceiptStatus, WorkStore

PERSON_STAGES = frozenset(
    {Stage.PERSON_DELIVERY, Stage.PERSON_ANSWER, Stage.PERSON_REVIEW, Stage.PERSON_BLOCKED}
)


class NoActivePolicy(RuntimeError):
    """No approved Policy is in force, so Eval has no rules to judge by."""


def status(store: WorkStore) -> dict[str, Any]:
    """The counts an operator needs at a glance. Healthy states are a few numbers, not a list."""
    open_tickets = store.open_tickets()
    effects = store.pending_effects()
    policy = store.active_policy()
    return {
        "paused": store.paused,
        "policy": None if policy is None else policy.version,
        "triggers": store.trigger_count(),
        "open_tickets": len(open_tickets),
        "stages": dict(sorted(Counter(stage_of(t).value for t in open_tickets).items())),
        "waiting_effects": len(effects),
        "failing_effects": sum(1 for effect in effects if effect.last_error is not None),
        "attention": len(attention(store)),
    }


def tickets(store: WorkStore) -> list[dict[str, Any]]:
    """Each open Ticket with its stage, its Thread and the rules it was accepted under."""
    return [
        {
            "id": ticket.id,
            "stage": stage_of(ticket).value,
            "thread": ticket.thread,
            "source": ticket.mandate.source,
            "rules": list(ticket.mandate.rules),
            "latest_report": None if ticket.latest_report is None else ticket.latest_report.value,
        }
        for ticket in store.open_tickets()
    ]


def attention(store: WorkStore) -> list[dict[str, Any]]:
    """What needs a person: Tickets waiting on one, notices, failing effects and failing sources."""
    items: list[dict[str, Any]] = []
    for ticket in store.open_tickets():
        stage = stage_of(ticket)
        if stage in PERSON_STAGES:
            items.append({"kind": "ticket", "id": ticket.id, "detail": stage.value})
    for effect in store.pending_effects():
        if effect.kind == NOTICE:
            items.append(
                {
                    "kind": "policy_notice",
                    "id": effect.key,
                    "detail": f"policy changed to {effect.payload.get('policy')}",
                }
            )
        elif effect.kind == RECOVERY:
            items.append(
                {
                    "kind": "recovery",
                    "id": effect.key,
                    "detail": "a run was interrupted by a restart; rerun it or stop it",
                }
            )
        elif effect.last_error is not None:
            items.append(
                {"kind": "effect", "id": f"{effect.kind}:{effect.key}", "detail": effect.last_error}
            )
    for source, errors in store.all_source_errors().items():
        for item, message in errors.items():
            items.append({"kind": "source", "id": f"{source}:{item}", "detail": message})
    return items


def stop(store: WorkStore, ticket_id: str) -> int | None:
    """End a Ticket, and drop its replies still waiting to be sent. Returns the process group of its
    run when one is running, else None (section 10 of the record).

    The caller ends that group with `executors.end_process_group` once it has closed the store, since
    ending it can take a few seconds. A Ticket that is not open raises KeyError. A run that has not
    yet recorded its process is ended by the driver as soon as it does.
    """
    ticket = store.ticket(ticket_id)
    if ticket is None or ticket.ended:
        raise KeyError(ticket_id)
    pid = None
    if ticket.assignment is not None and ticket.assignment.state is AssignmentState.RUNNING:
        pid = ticket.assignment.pid
    with store.transaction():
        store.save_ticket(replace(ticket, ended=True))
        for receipt in store.pending_receipts(ticket_id):
            store.settle_receipt(receipt.id, ReceiptStatus.DROPPED, "stopped")
        store.cancel_effect(REPLY, ticket_id)
    return pid


def runs(store: WorkStore, ticket_id: str) -> list[dict[str, Any]]:
    """Each run of a Ticket, oldest first: its result, and the tail of its output. The output is
    text from a program the agent does not trust, so a reader treats it as data. Raises KeyError for
    an unknown Ticket."""
    if store.ticket(ticket_id) is None:
        raise KeyError(ticket_id)
    return [
        {
            "assignment": run.assignment_id,
            "at": run.at,
            "ok": run.ok,
            "reason": run.reason,
            "stdout": run.stdout,
            "stderr": run.stderr,
        }
        for run in store.runs_of(ticket_id)
    ]


def rerun(store: WorkStore, ticket_id: str) -> str:
    """Start again a Ticket that a restart interrupted, in the same directory. Returns the id of its
    new Assignment. Raises KeyError for an unknown or stopped Ticket, and ValueError when the Ticket
    is not waiting for a rerun."""
    return requeue(store, ticket_id)


def pause(store: WorkStore) -> None:
    store.set_paused(True)


def resume(store: WorkStore) -> None:
    store.set_paused(False)


def retry(store: WorkStore, kind: str | None = None) -> int:
    """Make the waiting effects due now, all of them or one kind. Returns how many."""
    return store.retry_effects(kind)


def label(store: WorkStore, decision_id: str, verdict: Verdict) -> None:
    """Record a person's verdict on a Decision. The latest verdict stands. An unknown Decision
    raises KeyError."""
    store.label(decision_id, verdict)


def adopt(store: WorkStore, policy: Policy, *, signature: bytes, trust: TrustStore) -> list[str]:
    """Adopt an approver-signed Policy, and return the ids of the Tickets it notified.

    Raises PolicyRejected, and stores nothing, when no approver in `trust` signed the Policy.
    """
    return governance.adopt(store, policy, signature=signature, trust=trust)


def evaluate_triggers(store: WorkStore, *, row: str, listens: Listens | None = None) -> EvalReport:
    """Decide the undecided Triggers under the Policy in force. Each Trigger arrived in `row`. With
    `listens`, only the Triggers it accepts are decided (per-scope listening, OPEN_DECISIONS item 4)."""
    policy = store.active_policy()
    if policy is None:
        raise NoActivePolicy("no approved Policy is in force; adopt one before evaluating")
    return evaluate(
        store,
        policy,
        RuleAssessor(policy.rules),
        lambda _: ScopeFacts(listened=True, observed=True, row=row),
        listens=listens,
    )
