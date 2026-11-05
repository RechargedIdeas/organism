"""v1.11 MoA routing: "email address" phrases that are not extraction requests stay unsure."""

from __future__ import annotations

from pathlib import Path

from organism_sdk.moa import shadow
from organism_sdk.moa.reference import reference_experts
from organism_sdk.moa.scorer import ROUTE_UNSURE, LexicalScorer

DATA = Path(__file__).parent / "data" / "moa_routing_email_recall.json"


def test_email_address_negatives_stay_unsure() -> None:
    # Adding "email address" as an extractor keyword sent these to the extractor: extraction
    # precision fell to 7/11 on this set, below the 0.90 gate. Keep them unsure until a context
    # rule can tell "set up an email address" from "pull the email address out of this text".
    rows = [row for row in shadow.load_labeled(DATA) if row.label == shadow.UNSURE]
    assert len(rows) == 4
    scorer = LexicalScorer()
    for row in rows:
        assert scorer.decide(row.query, reference_experts()).route == ROUTE_UNSURE, row.query
