"""v1.11 MoA routing: a fresh labelled set for the email recall misses (O4, S2).

The set was written from each query's meaning, before the rule that covers its recall misses. The
two strict expected failures below are wrong routes already in the rule: a cue verb counts wherever
it appears, so "get" in "should the new hire get" and the noun "list" both route to the extractor.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from organism_sdk.moa import shadow
from organism_sdk.moa.reference import reference_experts
from organism_sdk.moa.scorer import ROUTE_EXPERT, ROUTE_UNSURE, LexicalScorer

FRESH = Path(__file__).parent / "data" / "moa_routing_recall_fresh.json"
WRONG_ROUTE_GET = "Which email address should the new hire get?"
WRONG_ROUTE_LIST = "Which email addresses are allowed to post to the all-staff list?"


def _decisions() -> list[tuple[shadow.LabeledQuery, object]]:
    scorer = LexicalScorer()
    return [(row, scorer.decide(row.query, reference_experts())) for row in shadow.load_labeled(FRESH)]


def _route(query: str) -> str:
    return LexicalScorer().decide(query, reference_experts()).route


def test_fresh_set_negatives_stay_unsure() -> None:
    for row, decision in _decisions():
        if row.label == shadow.UNSURE and row.query not in (WRONG_ROUTE_GET, WRONG_ROUTE_LIST):
            assert decision.route == ROUTE_UNSURE, row.query


def test_fresh_set_never_routes_to_the_wrong_expert() -> None:
    for row, decision in _decisions():
        if row.label != shadow.UNSURE and decision.route == ROUTE_EXPERT:
            assert decision.expert_id == row.label, row.query


@pytest.mark.xfail(strict=True, reason="O4: 'get' is a cue wherever it appears, so this routes to the extractor")
def test_get_as_a_plain_verb_does_not_route_to_extractor() -> None:
    assert _route(WRONG_ROUTE_GET) == ROUTE_UNSURE


@pytest.mark.xfail(strict=True, reason="O4: the noun 'list' is a cue wherever it appears, so this routes")
def test_noun_list_does_not_route_to_extractor() -> None:
    assert _route(WRONG_ROUTE_LIST) == ROUTE_UNSURE


@pytest.mark.xfail(strict=True, reason="recall: verb-less extraction requests stay unsure until the rule covers them")
def test_fresh_set_extraction_recall() -> None:
    reached = sum(1 for row, d in _decisions() if row.label == "extractor" and d.route == ROUTE_EXPERT)
    assert reached == 8
