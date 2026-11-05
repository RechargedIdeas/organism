"""v1.12 W8, follow-ups: a Ticket owns its Thread, and a human message there goes to its executor.

The property tests build random states from a fixed seed, so a failure can be replayed. They
check the routing against a plain reference model, and against the store's own lookup."""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from organism_sdk.work.domain import Addressed, Mandate, Strength, Ticket, Trigger, Via
from organism_sdk.work.routing import ThreadOwnershipError, route
from organism_sdk.work.store import WorkStore

THREADS = ("github:octo/cat#1", "github:octo/cat#2", "github:octo/cat#3")
ACTORS = ("alice", "bob", "ci-bot")


def mandate() -> Mandate:
    return Mandate(
        policy_version="sha256:test",
        strength=Strength.EXPLICIT,
        via=Via.ADDRESSED,
        source="github",
        row="repo",
        sender="alice",
    )


def trigger(thread: str, *, human: bool = True, actor: str = "alice", n: int = 1) -> Trigger:
    return Trigger(
        id=f"m{n}",
        source="github",
        thread=thread,
        actor=actor,
        human=human,
        addressed=Addressed.NONE,
        at="2026-11-04T00:00:00Z",
        text="hello",
    )


def ticket(ticket_id: str, thread: str | None, *, ended: bool = False) -> Ticket:
    return Ticket(id=ticket_id, mandate=mandate(), ended=ended, thread=thread)


def test_a_human_message_on_an_owned_thread_goes_to_its_ticket() -> None:
    tickets = [ticket("t1", THREADS[0])]
    assert route(trigger(THREADS[0]), tickets) == "t1"


def test_a_bot_message_on_an_owned_thread_is_left_to_the_gate() -> None:
    tickets = [ticket("t1", THREADS[0])]
    assert route(trigger(THREADS[0], human=False, actor="ci-bot"), tickets) is None


def test_a_message_on_an_unowned_thread_is_not_routed() -> None:
    tickets = [ticket("t1", THREADS[0])]
    assert route(trigger(THREADS[1]), tickets) is None


def test_an_ended_ticket_owns_nothing() -> None:
    tickets = [ticket("t1", THREADS[0], ended=True)]
    assert route(trigger(THREADS[0]), tickets) is None


def test_a_ticket_without_a_thread_owns_nothing() -> None:
    assert route(trigger(THREADS[0]), [ticket("t1", None)]) is None


def test_two_open_owners_of_one_thread_are_refused_whatever_arrives() -> None:
    tickets = [ticket("t1", THREADS[0]), ticket("t2", THREADS[0])]
    with pytest.raises(ThreadOwnershipError):
        route(trigger(THREADS[0]), tickets)
    with pytest.raises(ThreadOwnershipError):
        route(trigger(THREADS[0], human=False, actor="ci-bot"), tickets)


def random_state(rng: random.Random) -> list[Ticket]:
    """At most one open Ticket per Thread, plus any number of ended ones."""
    tickets: list[Ticket] = []
    for index, thread in enumerate(THREADS):
        if rng.random() < 0.6:
            tickets.append(ticket(f"open-{index}", thread))
        for number in range(rng.randrange(3)):
            tickets.append(ticket(f"ended-{index}-{number}", thread, ended=True))
    rng.shuffle(tickets)
    return tickets


def reference(trigger_in: Trigger, tickets: list[Ticket]) -> str | None:
    """The plain rule, written out: the one open owner of a human message's Thread, or None."""
    if not trigger_in.human:
        return None
    for owned in tickets:
        if not owned.ended and owned.thread == trigger_in.thread:
            return owned.id
    return None


@pytest.mark.parametrize("seed", range(200))
def test_routing_matches_the_reference_on_random_states(seed: int) -> None:
    rng = random.Random(seed)
    tickets = random_state(rng)
    for number in range(10):
        message = trigger(
            rng.choice(THREADS),
            human=rng.random() < 0.7,
            actor=rng.choice(ACTORS),
            n=number,
        )
        assert route(message, tickets) == reference(message, tickets)


@pytest.mark.parametrize("seed", range(50))
def test_routing_does_not_depend_on_the_order_of_the_tickets(seed: int) -> None:
    rng = random.Random(seed)
    tickets = random_state(rng)
    shuffled = list(reversed(tickets))
    for thread in THREADS:
        message = trigger(thread)
        assert route(message, tickets) == route(message, shuffled)


@pytest.mark.parametrize("seed", range(40))
def test_routing_agrees_with_the_store_about_who_owns_a_thread(tmp_path: Path, seed: int) -> None:
    rng = random.Random(seed)
    tickets = random_state(rng)
    with WorkStore(tmp_path / f"{seed}.sqlite") as store:
        for stored in tickets:
            store.save_ticket(stored)
        for thread in THREADS:
            owner = store.ticket_for_thread(thread)
            routed = route(trigger(thread), tickets)
            assert routed == (owner.id if owner is not None else None)
