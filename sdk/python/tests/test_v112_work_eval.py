"""v1.12 Eval over the store: each Trigger decided once per Policy version, and retried when unavailable."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from organism_sdk.work.assess import Assessment, RuleAssessor
from organism_sdk.work.decide import EvalReason
from organism_sdk.work.domain import (
    Addressed,
    Mandate,
    Outcome,
    Strength,
    Ticket,
    Trigger,
    Verdict,
    Via,
    decision_key,
)
from organism_sdk.work.gate import Reason, ScopeFacts
from organism_sdk.work.policy import AcceptMode, AdmissionRow, Policy, Rule, SourcePolicy
from organism_sdk.work.promote import MIN_LABELED, graduate
from organism_sdk.work.runner import DEADLINE_S, EvalReport, evaluate
from organism_sdk.work.store import WorkStore

CI = Rule(id="ci-fix", instruction="fix CI", pattern="CI")
OBSERVED = ScopeFacts(listened=True, observed=True, row="repo")


class Clock:
    """A clock the test moves by hand."""

    def __init__(self, now: float = 10_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class BrokenAssessor(RuleAssessor):
    """An assessor that is down: every assessment fails."""

    def __init__(self) -> None:
        super().__init__(())

    def assess(self, trigger: Trigger) -> Assessment:
        raise RuntimeError("model backend is down")


def policy(mode: AcceptMode, *rules: Rule) -> Policy:
    part = SourcePolicy(
        source="github", allowed=frozenset({"Alice"}), rows={"repo": AdmissionRow()}
    )
    return Policy(mode=mode, rules=rules, sources=(part,))


def trigger(
    n: int,
    text: str,
    *,
    actor: str = "alice",
    addressed: Addressed = Addressed.NONE,
) -> Trigger:
    return Trigger(
        id=f"m{n}",
        source="github",
        thread="github:issue-1",
        actor=actor,
        human=True,
        addressed=addressed,
        at=f"2026-11-04T00:00:{n:02d}Z",
        text=text,
    )


def ticket(pol: Policy, *, ended: bool = False) -> Ticket:
    mandate = Mandate(
        policy_version=pol.version,
        strength=Strength.EXPLICIT,
        via=Via.ADDRESSED,
        source="github",
        row="repo",
        sender="alice",
    )
    return Ticket(id="t1", mandate=mandate, ended=ended, thread="github:issue-1")


def run(store: WorkStore, pol: Policy, assessor: RuleAssessor | None = None) -> EvalReport:
    return evaluate(store, pol, assessor or RuleAssessor(pol.rules), lambda _: OBSERVED)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(tmp_path: Path, clock: Clock) -> Iterator[WorkStore]:
    handle = WorkStore(tmp_path / "work.sqlite", clock=clock)
    yield handle
    handle.close()


def test_a_trigger_is_decided_once_per_policy_version(store: WorkStore) -> None:
    pol = policy(AcceptMode.OBSERVE, CI)
    store.receive(trigger(1, "CI is red"))
    assert run(store, pol) == EvalReport(decided=1, unavailable=0)
    assert run(store, pol) == EvalReport(decided=0, unavailable=0)
    assert [d.id for d in store.all_decisions()] == [decision_key("m1", pol.version)]


def test_an_explicit_request_is_accepted_and_recorded(store: WorkStore) -> None:
    pol = policy(AcceptMode.OFF, CI)
    store.receive(trigger(1, "please look", addressed=Addressed.MENTION))
    run(store, pol)
    [decision] = store.all_decisions()
    assert decision.outcome is Outcome.ACCEPT
    assert decision.reasons == (Reason.ADDRESSED_BY_LISTED.value,)


def test_an_unavailable_assessment_is_left_for_the_next_run(store: WorkStore) -> None:
    pol = policy(AcceptMode.AUTO, CI)
    store.receive(trigger(1, "CI is red"))
    assert run(store, pol, BrokenAssessor()) == EvalReport(decided=0, unavailable=1)
    assert store.all_decisions() == []
    assert run(store, pol) == EvalReport(decided=1, unavailable=0)
    [decision] = store.all_decisions()
    assert EvalReason.WOULD_ACCEPT.value in decision.reasons


def test_a_late_trigger_is_ignored_not_acted_on(store: WorkStore, clock: Clock) -> None:
    pol = policy(AcceptMode.AUTO, Rule(id="ci-fix", instruction="fix CI", pattern="CI", auto=True))
    store.receive(trigger(1, "CI is red"))
    clock.now += DEADLINE_S + 1
    run(store, pol)
    [decision] = store.all_decisions()
    assert decision.outcome is Outcome.IGNORE
    assert EvalReason.DEADLINE_PASSED.value in decision.reasons


def test_a_reply_on_an_open_ticket_is_a_followup(store: WorkStore) -> None:
    pol = policy(AcceptMode.OBSERVE, CI)
    store.save_ticket(ticket(pol))
    store.receive(trigger(1, "any news?", actor="bob"))
    run(store, pol)
    [decision] = store.all_decisions()
    assert decision.reasons[0] == Reason.FOLLOWUP_UNLISTED.value


def test_an_ended_ticket_does_not_make_a_reply_a_followup(store: WorkStore) -> None:
    pol = policy(AcceptMode.OBSERVE, CI)
    store.save_ticket(ticket(pol, ended=True))
    store.receive(trigger(1, "any news?", actor="bob"))
    run(store, pol)
    [decision] = store.all_decisions()
    assert decision.reasons[0] == Reason.CELL_IGNORED.value


def test_labels_keep_the_latest_verdict_and_refuse_unknown_decisions(store: WorkStore) -> None:
    pol = policy(AcceptMode.OBSERVE, CI)
    store.receive(trigger(1, "CI is red"))
    run(store, pol)
    [decision] = store.all_decisions()
    store.label(decision.id, Verdict.AGREE)
    store.label(decision.id, Verdict.DISAGREE)
    assert store.labels() == {decision.id: Verdict.DISAGREE}
    with pytest.raises(KeyError):
        store.label("m9@nope", Verdict.AGREE)


def test_a_graduated_rule_accepts_new_work_but_not_the_old_backlog(
    store: WorkStore, clock: Clock
) -> None:
    pol = policy(AcceptMode.AUTO, CI)
    for n in range(MIN_LABELED):
        store.receive(trigger(n, f"CI is red {n}"))
    run(store, pol)
    for decision in store.all_decisions():
        store.label(decision.id, Verdict.AGREE)

    graduated = graduate(pol, store.all_decisions(), store.labels())
    assert graduated.rules[0].auto is True

    clock.now += DEADLINE_S + 1  # the backlog is now past its deadline
    store.receive(trigger(99, "CI is red again"))
    run(store, graduated)

    fresh = [d for d in store.all_decisions() if d.trigger_id == "m99"]
    assert [d.outcome for d in fresh] == [Outcome.ACCEPT]
    backlog = [d for d in store.all_decisions() if d.id.endswith(graduated.version)]
    backlog = [d for d in backlog if d.trigger_id != "m99"]
    assert len(backlog) == MIN_LABELED
    assert all(EvalReason.DEADLINE_PASSED.value in d.reasons for d in backlog)
