"""v1.11 MoA routing: a fresh labelled set for the email recall misses (O4, S2).

The set was written from each query's meaning, before the rule that covers its recall misses. Under
that rule every negative stays unsure, and no query reaches the wrong expert. The one extraction
request left unrouted has no verb, no question opener and no reference to supplied text, so it is a
recall miss that the rule does not claim.
"""

from __future__ import annotations

from pathlib import Path

from organism_sdk.moa import shadow
from organism_sdk.moa.reference import reference_experts
from organism_sdk.moa.scorer import ROUTE_EXPERT, ROUTE_UNSURE, LexicalScorer, RouteDecision

FRESH = Path(__file__).parent / "data" / "moa_routing_recall_fresh.json"
WRONG_ROUTE_GET = "Which email address should the new hire get?"
WRONG_ROUTE_LIST = "Which email addresses are allowed to post to the all-staff list?"


def _decisions() -> list[tuple[shadow.LabeledQuery, RouteDecision]]:
    scorer = LexicalScorer()
    return [(row, scorer.decide(row.query, reference_experts())) for row in shadow.load_labeled(FRESH)]


def _route(query: str) -> str:
    return LexicalScorer().decide(query, reference_experts()).route


def test_fresh_set_negatives_stay_unsure() -> None:
    for row, decision in _decisions():
        if row.label == shadow.UNSURE:
            assert decision.route == ROUTE_UNSURE, row.query


def test_fresh_set_never_routes_to_the_wrong_expert() -> None:
    for row, decision in _decisions():
        if row.label != shadow.UNSURE and decision.route == ROUTE_EXPERT:
            assert decision.expert_id == row.label, row.query


def test_get_as_a_plain_verb_does_not_route_to_extractor() -> None:
    # O4: "get" counted wherever it appeared. It now counts only when it opens the request.
    assert _route(WRONG_ROUTE_GET) == ROUTE_UNSURE


def test_noun_list_does_not_route_to_extractor() -> None:
    # O4: the noun "list" counted wherever it appeared. It now counts only when it opens the request.
    assert _route(WRONG_ROUTE_LIST) == ROUTE_UNSURE


def test_fresh_set_extraction_recall() -> None:
    # Seven of the eight extraction requests reach the extractor. The eighth, "Email addresses in this
    # export, please", opens with a noun phrase and has no verb or question opener: a recall miss.
    reached = sum(1 for row, d in _decisions() if row.label == "extractor" and d.route == ROUTE_EXPERT)
    assert reached == 7


def test_request_after_a_polite_lead_routes_to_extractor() -> None:
    # The cue counts after "please" or "can you", as well as at the start of the query.
    assert _route("Please pull the email addresses out of this list: ann@a.io") == ROUTE_EXPERT
    assert _route("Can you pull the email addresses out of this list: ann@a.io") == ROUTE_EXPERT
