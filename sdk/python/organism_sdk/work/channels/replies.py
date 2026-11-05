"""Replies to a Ticket's Thread, sent once and in order (v1.12 W6). Design record: docs/v1.12/WORK_AGENT.md.

A reply is a receipt, queued by `queue_reply`. Each Ticket has one reply effect at a time, keyed
by the Ticket id, and it carries the oldest pending receipt of that Ticket. When that receipt
settles, the next pending one is queued. So a Ticket's replies leave in the order they were
written, and a reply that fails holds the ones behind it.

The handler exists only while external writes are enabled. Without it, `reply_handlers` is
empty, the effects wait in the queue, and nothing reaches GitHub.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from organism_sdk.work.channels.github import ChannelGone, GitHubChannel
from organism_sdk.work.store import ReceiptStatus, WorkStore

REPLY = "reply"
Handler = Callable[[Mapping[str, Any]], None]


def queue_reply(
    store: WorkStore, *, ticket_id: str, receipt_id: str, conversation: str, text: str
) -> bool:
    """Add a reply for a Ticket and queue the next one to send. True when the receipt is new."""
    new = store.add_receipt(receipt_id, ticket_id=ticket_id, conversation=conversation, text=text)
    queue_next_reply(store, ticket_id)
    return new


def queue_next_reply(store: WorkStore, ticket_id: str) -> None:
    """Queue the oldest pending reply of a Ticket, if it has one."""
    pending = store.pending_receipts(ticket_id)
    if not pending:
        return
    head = pending[0]
    store.enqueue(
        REPLY,
        ticket_id,
        {
            "ticket": ticket_id,
            "receipt": head.id,
            "conversation": head.conversation,
            "text": head.text,
        },
    )


def reply_handlers(
    store: WorkStore, channel: GitHubChannel, *, enabled: bool
) -> dict[str, Handler]:
    """The handler for queued replies. Empty while external writes are off, so none is sent."""
    if not enabled:
        return {}

    def deliver(payload: Mapping[str, Any]) -> None:
        receipt = str(payload["receipt"])
        try:
            channel.send(
                receipt=receipt,
                conversation=str(payload["conversation"]),
                text=str(payload["text"]),
            )
        except ChannelGone:
            store.settle_receipt(receipt, ReceiptStatus.DROPPED, "gone")
        else:
            store.settle_receipt(receipt, ReceiptStatus.SENT)
        queue_next_reply(store, str(payload["ticket"]))

    return {REPLY: deliver}
