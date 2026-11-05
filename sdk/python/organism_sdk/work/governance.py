"""Policy governance (v1.12 W9). Design record: docs/v1.12/WORK_AGENT.md.

A Policy takes effect only when an approver has signed its version. The agent checks the
signature against the approvers in its TrustStore, and never signs. A Policy change notifies only
the live Tickets it affects: those whose Mandate uses a rule that changed, or a Source part that
changed. It never cancels a Ticket.

`affected_tickets` and `policy_payload` are pure. `adopt` writes through the store, in one
transaction.
"""

from __future__ import annotations

from collections.abc import Iterable

from organism_sdk.signing import TrustStore, verify_any
from organism_sdk.work.domain import Strength, Ticket
from organism_sdk.work.policy import AcceptMode, Policy, instruction_hash
from organism_sdk.work.store import WorkStore

POLICY_DOMAIN = b"organism.work.policy.v1\n"
NOTICE = "policy_notice"


class PolicyRejected(ValueError):
    """The Policy is not signed by an approver in the trust store, so it does not take effect."""


def policy_payload(version: str) -> bytes:
    """What an approver signs: the Policy's version, under a domain prefix of its own."""
    return POLICY_DOMAIN + version.encode("ascii")


def is_approved(policy: Policy, signature: bytes, trust: TrustStore) -> bool:
    """True when an approver in the trust store signed this Policy's version.

    An author key does not count, and an empty trust store approves nothing.
    """
    return verify_any(trust.approvers, signature, policy_payload(policy.version))


def still_valid(ticket: Ticket, policy: Policy) -> bool:
    """True when the Ticket's Mandate still stands under `policy`.

    It stands when its Source part is still listed, every rule it names is still enabled, and an
    inferred Mandate still has the auto mode, the only mode that accepts inferred work. A Mandate is
    never rewritten: this only says whether it may still be relied on.
    """
    mandate = ticket.mandate
    if policy.source(mandate.source) is None:
        return False
    if mandate.strength is Strength.INFERRED and policy.mode is not AcceptMode.AUTO:
        return False
    enabled = {rule.id for rule in policy.rules if rule.enabled}
    return set(mandate.rules) <= enabled


def affected_tickets(old: Policy, new: Policy, tickets: Iterable[Ticket]) -> list[Ticket]:
    """The open Tickets a change from `old` to `new` touches, in the order given.

    A Ticket is affected when a rule its Mandate uses changed, or when the Source part its Mandate
    came from changed. A change to the accept mode affects no Ticket: it only decides admission
    from now on.
    """
    old_rules = {rule.id: rule for rule in old.rules}
    new_rules = {rule.id: rule for rule in new.rules}
    changed_rules = {
        rule_id
        for rule_id in old_rules.keys() | new_rules.keys()
        if old_rules.get(rule_id) != new_rules.get(rule_id)
    }
    sources = {part.source for part in old.sources} | {part.source for part in new.sources}
    changed_sources = {name for name in sources if old.source(name) != new.source(name)}
    return [
        ticket
        for ticket in tickets
        if not ticket.ended
        and (
            changed_rules.intersection(ticket.mandate.rules)
            or ticket.mandate.source in changed_sources
        )
    ]


def default_updated(store: WorkStore, ticket: Ticket, policy: Policy) -> bool:
    """True when the text of a rule the Ticket started with reads differently in `policy`: the
    "default updated" flag of W9. A rule that was removed, or only switched on, off or to auto, is
    not a text change. A Ticket that pinned no text reads the text of its Policy version."""
    current = {rule.id: instruction_hash(rule.instruction) for rule in policy.rules}
    if ticket.instructions:
        started = dict(ticket.instructions)
    else:
        old = store.policy(ticket.mandate.policy_version)
        matched = set(ticket.mandate.rules)
        started = (
            {}
            if old is None
            else {r.id: instruction_hash(r.instruction) for r in old.rules if r.id in matched}
        )
    return any(current.get(rule_id, digest) != digest for rule_id, digest in started.items())


def adopt(store: WorkStore, policy: Policy, *, signature: bytes, trust: TrustStore) -> list[str]:
    """Make an approved Policy the one in force, and notify the open Tickets it affects.

    Returns the ids of the Tickets notified. Each notice is an effect of kind `NOTICE`, keyed by
    the Ticket, which waits in the queue until a handler surfaces it. Nothing running is cancelled.
    Raises PolicyRejected, and stores nothing, when the signature is not an approver's.
    """
    if not is_approved(policy, signature, trust):
        raise PolicyRejected(f"policy {policy.version} is not signed by an approver")
    previous = store.active_policy()
    notified: list[str] = []
    with store.transaction():
        store.save_policy(policy, signature=signature)
        store.set_active_policy(policy.version)
        if previous is not None:
            for ticket in affected_tickets(previous, policy, store.open_tickets()):
                store.enqueue(
                    NOTICE,
                    ticket.id,
                    {
                        "policy": policy.version,
                        "previous": previous.version,
                        "default_updated": default_updated(store, ticket, policy),
                    },
                )
                notified.append(ticket.id)
    return notified
