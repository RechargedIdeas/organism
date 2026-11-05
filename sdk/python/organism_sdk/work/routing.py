"""Routing of a human message to the Ticket that owns its Thread (v1.12 W8). Design record: docs/v1.12/WORK_AGENT.md.

Pure. A Ticket owns its Thread while it is open. A human message on that Thread goes to the
Ticket's executor, and does not start a new Ticket. At most one open Ticket may own a Thread, so
the owner is never ambiguous. A bot message is not routed here: the gate decides it as before.

Hand-back, release and pull-request following are not built. They wait for shadow data (W8).
"""

from __future__ import annotations

from collections.abc import Iterable

from organism_sdk.work.domain import Ticket, Trigger


class ThreadOwnershipError(ValueError):
    """More than one open Ticket owns the same Thread. That state must never be reached."""


def route(trigger: Trigger, tickets: Iterable[Ticket]) -> str | None:
    """The id of the open Ticket that takes this Trigger, or None when no Ticket does.

    Only a human message on a Thread with an open owner is routed. The ownership check runs for
    every Trigger, so a broken state is reported whatever arrives on that Thread. Only
    ``trigger.thread`` is read here: ``related_threads`` are context and never route (section 3 of
    WORK_AGENT.md).
    """
    owners = [
        ticket.id for ticket in tickets if not ticket.ended and ticket.thread == trigger.thread
    ]
    if len(owners) > 1:
        raise ThreadOwnershipError(
            f"thread {trigger.thread} is owned by {len(owners)} open tickets: {sorted(owners)}"
        )
    if not trigger.human or not owners:
        return None
    return owners[0]
