"""v1.11 MoA routing: "email address" phrases that are not extraction requests stay unsure."""

from __future__ import annotations

from pathlib import Path

from organism_sdk.moa import shadow
from organism_sdk.moa.reference import reference_experts
from organism_sdk.moa.scorer import ROUTE_EXPERT, ROUTE_UNSURE, LexicalScorer

DATA = Path(__file__).parent / "data" / "moa_routing_email_recall.json"
FRESH = Path(__file__).parent / "data" / "moa_routing_email_context.json"


def test_email_address_negatives_stay_unsure() -> None:
    # Adding "email address" as a plain extractor keyword sent these to the extractor: extraction
    # precision fell to 7/11 on this set, below the 0.90 gate. The context rule (O4) counts the
    # phrase only beside a verb of retrieval, and none of these has one.
    rows = [row for row in shadow.load_labeled(DATA) if row.label == shadow.UNSURE]
    assert len(rows) == 4
    scorer = LexicalScorer()
    for row in rows:
        assert scorer.decide(row.query, reference_experts()).route == ROUTE_UNSURE, row.query


def test_the_context_rule_on_the_fresh_set_written_before_it() -> None:
    # S2: this set was written before the rule, from each query's meaning. Twelve of the twelve
    # extraction requests reach the extractor. "Which email addresses are in this export" opens with
    # a question and names the supplied text, so the question rule routes it (O4). No query goes to the
    # wrong expert, and every negative stays unsure.
    scorer = LexicalScorer()
    reached = 0
    for row in shadow.load_labeled(FRESH):
        decision = scorer.decide(row.query, reference_experts())
        if row.label == shadow.UNSURE:
            assert decision.route == ROUTE_UNSURE, row.query
            continue
        if decision.route == ROUTE_EXPERT:
            assert decision.expert_id == row.label, row.query
            if row.label == "extractor":
                reached += 1
    assert reached == 12
