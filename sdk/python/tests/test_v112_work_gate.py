"""v1.12 gate: the admission cells of the authorization document, and the invariants they imply."""

from __future__ import annotations

import itertools

import pytest
from organism_sdk.work.domain import Addressed, Strength, Trigger, Via
from organism_sdk.work.gate import Admission, Reason, ScopeFacts, admit
from organism_sdk.work.policy import (
    AcceptMode,
    AdmissionRow,
    Cell,
    Policy,
    Rule,
    SourcePolicy,
)

ROW = "repo"
UNOBSERVED = ScopeFacts(listened=True, observed=False, row=ROW)
OBSERVED = ScopeFacts(listened=True, observed=True, row=ROW)
NOT_ADMITTED = Strength.NOT_ADMITTED
INFERRED = Strength.INFERRED
EXPLICIT = Strength.EXPLICIT


def policy(
    *,
    mode: AcceptMode = AcceptMode.OBSERVE,
    row: AdmissionRow | None = None,
) -> Policy:
    github = SourcePolicy(
        source="github",
        allowed=frozenset({"Alice"}),
        bots=frozenset({"dependabot[bot]"}),
        rows={ROW: row or AdmissionRow()},
    )
    return Policy(
        mode=mode, rules=(Rule(id="ci-fix", instruction="fix failing CI"),), sources=(github,)
    )


def message(
    actor: str | None = "bob",
    *,
    human: bool = True,
    addressed: Addressed = Addressed.NONE,
    source: str = "github",
) -> Trigger:
    return Trigger(
        id="m1",
        source=source,
        thread="github:issue-1",
        actor=actor,
        human=human,
        addressed=addressed,
        at="2026-11-04T00:00:00Z",
        text="hello",
    )


MENTION = Addressed.MENTION


@pytest.mark.parametrize(
    ("subject", "scope", "pol", "has_tickets", "expected"),
    [
        # A listed person who addresses the agent is explicit, in every mode.
        (
            message("Alice", addressed=MENTION),
            OBSERVED,
            policy(mode=AcceptMode.OFF),
            False,
            Admission(EXPLICIT, Reason.ADDRESSED_BY_LISTED, Via.ADDRESSED),
        ),
        # Listing is case-insensitive.
        (
            message("ALICE", addressed=MENTION),
            UNOBSERVED,
            policy(),
            False,
            Admission(EXPLICIT, Reason.ADDRESSED_BY_LISTED, Via.ADDRESSED),
        ),
        # A listed person who does not address the agent takes the listed cell: inferred by default.
        (
            message("Alice"),
            OBSERVED,
            policy(),
            False,
            Admission(INFERRED, Reason.CELL_INFERRED, Via.ADMISSION),
        ),
        (
            message("Alice"),
            OBSERVED,
            policy(mode=AcceptMode.OFF),
            False,
            Admission(NOT_ADMITTED, Reason.MODE_OFF),
        ),
        (
            message("Alice"),
            UNOBSERVED,
            policy(),
            False,
            Admission(NOT_ADMITTED, Reason.NOT_OBSERVED),
        ),
        # An unlisted person who addresses the agent: ignored by default.
        (
            message(addressed=MENTION),
            UNOBSERVED,
            policy(),
            False,
            Admission(NOT_ADMITTED, Reason.CELL_IGNORED),
        ),
        (
            message(addressed=MENTION),
            UNOBSERVED,
            policy(row=AdmissionRow(unlisted_addressed=Cell.EXPLICIT)),
            False,
            Admission(EXPLICIT, Reason.CELL_EXPLICIT, Via.ADMISSION),
        ),
        (
            message(addressed=MENTION),
            UNOBSERVED,
            policy(row=AdmissionRow(unlisted_addressed=Cell.INFERRED)),
            False,
            Admission(INFERRED, Reason.CELL_INFERRED, Via.ADMISSION),
        ),
        # An explicit cell still works when inferred candidates are off.
        (
            message(addressed=MENTION),
            UNOBSERVED,
            policy(mode=AcceptMode.OFF, row=AdmissionRow(unlisted_addressed=Cell.EXPLICIT)),
            False,
            Admission(EXPLICIT, Reason.CELL_EXPLICIT, Via.ADMISSION),
        ),
        # An unlisted, unaddressed message: needs an observed scope, and is ignored by default.
        (message(), UNOBSERVED, policy(), False, Admission(NOT_ADMITTED, Reason.NOT_OBSERVED)),
        (message(), OBSERVED, policy(), False, Admission(NOT_ADMITTED, Reason.CELL_IGNORED)),
        (
            message(),
            OBSERVED,
            policy(row=AdmissionRow(unlisted_unaddressed=Cell.INFERRED)),
            False,
            Admission(INFERRED, Reason.CELL_INFERRED, Via.ADMISSION),
        ),
        # Scope and Source checks come first.
        (
            message("Alice", addressed=MENTION),
            ScopeFacts(listened=False, row=ROW),
            policy(),
            False,
            Admission(NOT_ADMITTED, Reason.NOT_LISTENED),
        ),
        (
            message("Alice", addressed=MENTION, source="feishu"),
            OBSERVED,
            policy(),
            False,
            Admission(NOT_ADMITTED, Reason.UNKNOWN_SOURCE),
        ),
        (
            message(addressed=MENTION),
            ScopeFacts(listened=True, row="other"),
            policy(),
            False,
            Admission(NOT_ADMITTED, Reason.NO_ROW),
        ),
        # A listed person's follow-up on a Thread with a Ticket is explicit, observed or not.
        (
            message("Alice"),
            UNOBSERVED,
            policy(mode=AcceptMode.OFF),
            True,
            Admission(EXPLICIT, Reason.FOLLOWUP_LISTED, Via.FOLLOWUP),
        ),
        # An unlisted person's follow-up is inferred, whatever the cell says.
        (
            message(),
            UNOBSERVED,
            policy(),
            True,
            Admission(INFERRED, Reason.FOLLOWUP_UNLISTED, Via.FOLLOWUP),
        ),
        (
            message(addressed=MENTION),
            UNOBSERVED,
            policy(),
            True,
            Admission(INFERRED, Reason.FOLLOWUP_UNLISTED, Via.FOLLOWUP),
        ),
        (
            message(),
            UNOBSERVED,
            policy(mode=AcceptMode.OFF),
            True,
            Admission(NOT_ADMITTED, Reason.MODE_OFF),
        ),
        # An unlisted person's addressed follow-up is explicit when its cell says so.
        (
            message(addressed=MENTION),
            UNOBSERVED,
            policy(row=AdmissionRow(unlisted_addressed=Cell.EXPLICIT)),
            True,
            Admission(EXPLICIT, Reason.CELL_EXPLICIT, Via.ADMISSION),
        ),
        # A listed bot that addresses the agent is inferred, never explicit.
        (
            message("dependabot[bot]", human=False, addressed=MENTION),
            UNOBSERVED,
            policy(),
            False,
            Admission(INFERRED, Reason.BOT_LISTED, Via.BOT),
        ),
        (
            message("dependabot[bot]", human=False),
            UNOBSERVED,
            policy(),
            False,
            Admission(NOT_ADMITTED, Reason.NOT_OBSERVED),
        ),
        (
            message("dependabot[bot]", human=False),
            OBSERVED,
            policy(),
            False,
            Admission(INFERRED, Reason.BOT_LISTED, Via.BOT),
        ),
        (
            message("dependabot[bot]", human=False),
            OBSERVED,
            policy(mode=AcceptMode.OFF),
            False,
            Admission(NOT_ADMITTED, Reason.MODE_OFF),
        ),
        (
            message("renovate[bot]", human=False, addressed=MENTION),
            OBSERVED,
            policy(),
            False,
            Admission(NOT_ADMITTED, Reason.NOT_A_LISTED_BOT),
        ),
        # An event with no sender, such as CI, takes only the last cell.
        (
            message(None, human=False),
            OBSERVED,
            policy(),
            False,
            Admission(NOT_ADMITTED, Reason.CELL_IGNORED),
        ),
        (
            message(None, human=False),
            OBSERVED,
            policy(row=AdmissionRow(unlisted_unaddressed=Cell.INFERRED)),
            False,
            Admission(INFERRED, Reason.CELL_INFERRED, Via.ADMISSION),
        ),
        (
            message(None, human=False),
            UNOBSERVED,
            policy(row=AdmissionRow(unlisted_unaddressed=Cell.INFERRED)),
            False,
            Admission(NOT_ADMITTED, Reason.NOT_OBSERVED),
        ),
    ],
)
def test_admission_follows_the_table(
    subject: Trigger,
    scope: ScopeFacts,
    pol: Policy,
    has_tickets: bool,
    expected: Admission,
) -> None:
    assert admit(subject, scope, pol, has_tickets=has_tickets) == expected


def _policies() -> list[tuple[Policy, AdmissionRow]]:
    cells = itertools.product(
        (Cell.EXPLICIT, Cell.INFERRED, Cell.IGNORE),
        (Cell.INFERRED, Cell.IGNORE),
        (Cell.INFERRED, Cell.IGNORE),
    )
    rows = [
        AdmissionRow(
            unlisted_addressed=addressed,
            listed_unaddressed=listed,
            unlisted_unaddressed=unlisted,
        )
        for addressed, listed, unlisted in cells
    ]
    return [(policy(mode=mode, row=row), row) for mode in AcceptMode for row in rows]


@pytest.mark.parametrize("actor", ["Alice", "bob", "dependabot[bot]", None])
@pytest.mark.parametrize("human", [True, False])
@pytest.mark.parametrize("addressed", list(Addressed))
@pytest.mark.parametrize("has_tickets", [False, True])
@pytest.mark.parametrize("observed", [False, True])
def test_invariants_hold_for_every_policy(
    actor: str | None, human: bool, addressed: Addressed, has_tickets: bool, observed: bool
) -> None:
    subject = message(actor, human=human, addressed=addressed)
    scope = ScopeFacts(listened=True, observed=observed, row=ROW)
    listed = actor is not None and actor.casefold() == "alice"
    bot = actor is not None and not human
    for pol, row in _policies():
        result = admit(subject, scope, pol, has_tickets=has_tickets)

        if result.strength is EXPLICIT:
            # Explicit needs a listed person, or an explicit cell on an addressed message.
            assert (human and listed) or (
                addressed is not Addressed.NONE and row.unlisted_addressed is Cell.EXPLICIT
            )
        if bot:
            assert result.strength is not EXPLICIT
        if pol.mode is AcceptMode.OFF:
            assert result.strength is not INFERRED
        if result.strength is NOT_ADMITTED:
            assert result.via is None
        else:
            assert result.via is not None
        # An unaddressed message needs an observed scope, unless it is a person's follow-up.
        if addressed is Addressed.NONE and not observed and not (has_tickets and human and actor):
            assert result.strength is NOT_ADMITTED
