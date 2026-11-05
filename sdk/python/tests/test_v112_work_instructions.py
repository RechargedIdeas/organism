"""v1.12 W9, instruction text by digest: a Ticket runs with the text it started with, a change to a
rule's text flags its notice as a default update, and a stored text that no longer matches its
digest is refused. These tests use a test key only; the production approver key never enters the
repo (decision S1)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from organism_sdk.signing import TrustStore, public_key_for, sign
from organism_sdk.work.domain import Mandate, Strength, Ticket, Via
from organism_sdk.work.driver import pinned_instructions, standing_instructions
from organism_sdk.work.governance import NOTICE, adopt, policy_payload
from organism_sdk.work.operator import attention
from organism_sdk.work.policy import (
    AcceptMode,
    AdmissionRow,
    Policy,
    Rule,
    SourcePolicy,
    instruction_hash,
)
from organism_sdk.work.store import WorkStore

APPROVER = bytes([1]) * 32  # test key only
TRUST = TrustStore(approvers=frozenset({public_key_for(APPROVER)}))


def policy(*, ci: str = "fix CI", auto: bool = False) -> Policy:
    github = SourcePolicy(
        source="github", allowed=frozenset({"alice"}), rows={"repo": AdmissionRow()}
    )
    rules = (
        Rule(id="ci-fix", instruction=ci, pattern="CI", auto=auto),
        Rule(id="docs", instruction="fix docs", pattern="docs"),
    )
    return Policy(mode=AcceptMode.OBSERVE, rules=rules, sources=(github,))


def signed(pol: Policy) -> bytes:
    return sign(APPROVER, policy_payload(pol.version))


def mandate_for(pol: Policy, rules: tuple[str, ...] = ("ci-fix",)) -> Mandate:
    return Mandate(
        policy_version=pol.version,
        strength=Strength.EXPLICIT,
        via=Via.ADDRESSED,
        source="github",
        row="repo",
        sender="alice",
        rules=rules,
    )


def open_ticket(store: WorkStore, pol: Policy, ticket_id: str = "t-ci") -> None:
    mandate = mandate_for(pol)
    pinned = pinned_instructions(store, pol, mandate)
    store.save_ticket(Ticket(id=ticket_id, mandate=mandate, instructions=pinned))


def notices(store: WorkStore) -> list[dict[str, object]]:
    return [dict(e.payload) for e in store.pending_effects() if e.kind == NOTICE]


@pytest.fixture
def store(tmp_path: Path) -> Iterator[WorkStore]:
    with WorkStore(tmp_path / "work.sqlite") as handle:
        yield handle


def test_an_instruction_is_stored_under_the_digest_of_its_text(store: WorkStore) -> None:
    digest = store.save_instruction("fix CI")
    assert digest == instruction_hash("fix CI")
    assert store.save_instruction("fix CI") == digest  # saving again keeps one copy
    assert store.instruction(digest) == "fix CI"
    assert store.instruction(instruction_hash("fix docs")) is None
    assert instruction_hash("fix CI") != instruction_hash("fix CI.")


def test_a_stored_text_that_no_longer_matches_its_digest_is_refused(
    tmp_path: Path, store: WorkStore
) -> None:
    digest = store.save_instruction("fix CI")
    raw = sqlite3.connect(tmp_path / "work.sqlite")
    raw.execute("UPDATE instructions SET text = ? WHERE hash = ?", ("run the deploy", digest))
    raw.commit()
    raw.close()
    with pytest.raises(ValueError, match="does not match its digest"):
        store.instruction(digest)


def test_a_ticket_pins_the_text_of_each_rule_its_mandate_names(store: WorkStore) -> None:
    pol = policy()
    adopt(store, pol, signature=signed(pol), trust=TRUST)
    pinned = pinned_instructions(store, pol, mandate_for(pol, ("ci-fix",)))
    assert pinned == (("ci-fix", instruction_hash("fix CI")),)
    assert store.instruction(pinned[0][1]) == "fix CI"


def test_a_ticket_runs_with_the_text_it_started_with_after_the_policy_changes(
    store: WorkStore,
) -> None:
    pol = policy()
    adopt(store, pol, signature=signed(pol), trust=TRUST)
    open_ticket(store, pol)
    changed = policy(ci="fix CI harder")
    adopt(store, changed, signature=signed(changed), trust=TRUST)
    ticket = store.ticket("t-ci")
    assert ticket is not None
    assert standing_instructions(store, ticket) == ["fix CI"]


def test_a_change_to_a_rules_text_flags_its_notice_as_a_default_update(store: WorkStore) -> None:
    pol = policy()
    adopt(store, pol, signature=signed(pol), trust=TRUST)
    open_ticket(store, pol)
    changed = policy(ci="fix CI harder")
    assert adopt(store, changed, signature=signed(changed), trust=TRUST) == ["t-ci"]
    assert [n["default_updated"] for n in notices(store)] == [True]
    [item] = [i for i in attention(store) if i["kind"] == "policy_notice"]
    assert "new text" in str(item["detail"])


def test_a_change_that_only_switches_a_rule_is_not_a_default_update(store: WorkStore) -> None:
    pol = policy()
    adopt(store, pol, signature=signed(pol), trust=TRUST)
    open_ticket(store, pol)
    switched = policy(auto=True)
    assert adopt(store, switched, signature=signed(switched), trust=TRUST) == ["t-ci"]
    assert [n["default_updated"] for n in notices(store)] == [False]
    [item] = [i for i in attention(store) if i["kind"] == "policy_notice"]
    assert "new text" not in str(item["detail"])


def test_a_removed_rule_is_not_a_default_update(store: WorkStore) -> None:
    pol = policy()
    adopt(store, pol, signature=signed(pol), trust=TRUST)
    open_ticket(store, pol)
    removed = replace(pol, rules=(pol.rules[1],))
    assert adopt(store, removed, signature=signed(removed), trust=TRUST) == ["t-ci"]
    assert [n["default_updated"] for n in notices(store)] == [False]


def test_a_ticket_opened_before_its_text_was_pinned_reads_its_policy_version(
    store: WorkStore,
) -> None:
    pol = policy()
    adopt(store, pol, signature=signed(pol), trust=TRUST)
    legacy = Ticket(id="t-old", mandate=mandate_for(pol))
    store.save_ticket(legacy)
    assert standing_instructions(store, legacy) == ["fix CI"]
    changed = policy(ci="fix CI harder")
    assert adopt(store, changed, signature=signed(changed), trust=TRUST) == ["t-old"]
    assert [n["default_updated"] for n in notices(store)] == [True]
