"""v1.12 W9, policy governance: a Policy takes effect only when an approver signs it, and a change
notifies only the Tickets it touches. These tests use test keys only; the production approver key
never enters the repo (decision S1)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from organism_sdk.signing import TrustStore, public_key_for, sign
from organism_sdk.work.domain import Mandate, Strength, Ticket, Via
from organism_sdk.work.governance import (
    NOTICE,
    PolicyRejected,
    adopt,
    is_approved,
    policy_payload,
)
from organism_sdk.work.policy import AcceptMode, AdmissionRow, Cell, Policy, Rule, SourcePolicy
from organism_sdk.work.store import WorkStore

APPROVER = bytes([1]) * 32  # test key only
AUTHOR = bytes([2]) * 32  # test key only
TRUST = TrustStore(
    authors=frozenset({public_key_for(AUTHOR)}),
    approvers=frozenset({public_key_for(APPROVER)}),
)


def policy(
    *,
    instruction: str = "fix CI",
    feishu_allowed: str = "bob",
    mode: AcceptMode = AcceptMode.OBSERVE,
) -> Policy:
    github = SourcePolicy(
        source="github",
        allowed=frozenset({"Alice"}),
        rows={"repo": AdmissionRow(unlisted_addressed=Cell.EXPLICIT)},
    )
    feishu = SourcePolicy(source="feishu", allowed=frozenset({feishu_allowed}))
    rules = (
        Rule(id="ci-fix", instruction=instruction, pattern="CI"),
        Rule(id="docs", instruction="fix docs", pattern="docs"),
    )
    return Policy(mode=mode, rules=rules, sources=(github, feishu))


def signed(pol: Policy, seed: bytes = APPROVER) -> bytes:
    return sign(seed, policy_payload(pol.version))


def ticket(
    store: WorkStore,
    ticket_id: str,
    *,
    rules: tuple[str, ...] = ("ci-fix",),
    source: str = "github",
    ended: bool = False,
) -> None:
    mandate = Mandate(
        policy_version="sha256:test",
        strength=Strength.EXPLICIT,
        via=Via.ADDRESSED,
        source=source,
        row="repo",
        sender="alice",
        rules=rules,
    )
    store.save_ticket(Ticket(id=ticket_id, mandate=mandate, ended=ended))


@pytest.fixture
def store(tmp_path: Path) -> Iterator[WorkStore]:
    with WorkStore(tmp_path / "work.sqlite") as handle:
        yield handle


def test_an_approved_policy_is_adopted_and_reads_back_whole(store: WorkStore) -> None:
    pol = policy()
    assert adopt(store, pol, signature=signed(pol), trust=TRUST) == []
    assert store.active_policy() == pol
    assert store.policy(pol.version) == pol
    assert store.policy_signature(pol.version) == signed(pol)


def test_a_policy_signed_by_an_author_is_refused_and_stores_nothing(store: WorkStore) -> None:
    pol = policy()
    with pytest.raises(PolicyRejected):
        adopt(store, pol, signature=signed(pol, seed=AUTHOR), trust=TRUST)
    assert store.active_policy() is None
    assert store.policy(pol.version) is None


def test_a_signature_over_another_policy_is_refused(store: WorkStore) -> None:
    approved = policy()
    changed = policy(instruction="fix CI in a new way")
    with pytest.raises(PolicyRejected):
        adopt(store, changed, signature=signed(approved), trust=TRUST)
    assert store.active_policy() is None


def test_a_malformed_signature_and_an_empty_trust_store_approve_nothing() -> None:
    pol = policy()
    assert is_approved(pol, bytes(64), TRUST) is False
    assert is_approved(pol, signed(pol), TrustStore()) is False
    assert is_approved(pol, b"short", TRUST) is False


def test_a_change_to_a_rule_notifies_only_the_tickets_that_use_it(store: WorkStore) -> None:
    adopt(store, policy(), signature=signed(policy()), trust=TRUST)
    ticket(store, "t-ci", rules=("ci-fix",))
    ticket(store, "t-docs", rules=("docs",))
    ticket(store, "t-feishu", rules=("docs",), source="feishu")
    ticket(store, "t-ended", rules=("ci-fix",), ended=True)
    changed = policy(instruction="fix CI harder")
    assert adopt(store, changed, signature=signed(changed), trust=TRUST) == ["t-ci"]
    notices = [effect.key for effect in store.pending_effects() if effect.kind == NOTICE]
    assert notices == ["t-ci"]


def test_a_change_to_a_source_notifies_the_tickets_from_that_source(store: WorkStore) -> None:
    adopt(store, policy(), signature=signed(policy()), trust=TRUST)
    ticket(store, "t-ci", rules=("ci-fix",))
    ticket(store, "t-feishu", rules=("docs",), source="feishu")
    changed = policy(feishu_allowed="carol")
    assert adopt(store, changed, signature=signed(changed), trust=TRUST) == ["t-feishu"]


def test_nothing_running_is_cancelled_by_a_change(store: WorkStore) -> None:
    adopt(store, policy(), signature=signed(policy()), trust=TRUST)
    ticket(store, "t-ci", rules=("ci-fix",))
    changed = policy(instruction="fix CI harder")
    adopt(store, changed, signature=signed(changed), trust=TRUST)
    survivor = store.ticket("t-ci")
    assert survivor is not None
    assert survivor.ended is False


def test_an_accept_mode_change_notifies_no_one(store: WorkStore) -> None:
    adopt(store, policy(), signature=signed(policy()), trust=TRUST)
    ticket(store, "t-ci", rules=("ci-fix",))
    auto = policy(mode=AcceptMode.AUTO)
    assert adopt(store, auto, signature=signed(auto), trust=TRUST) == []
    assert store.active_policy() == auto
