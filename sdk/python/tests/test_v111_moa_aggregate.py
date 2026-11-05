"""v1.11 MoA aggregation: selection rules and VSA provenance recovery."""

from __future__ import annotations

import random

import pytest
from organism_sdk.moa.aggregate import (
    MAX_EXPERTS_PER_REQUEST,
    aggregate,
    composite_of,
    select,
    verify,
)
from organism_sdk.moa.experts import ExpertOutput


def _out(eid: str, payload: str, confidence: float, valid: bool = True) -> ExpertOutput:
    return ExpertOutput(eid, payload, confidence, valid)


def test_select_picks_highest_confidence_schema_valid_output() -> None:
    outs = [_out("a", "{}", 0.4), _out("b", "{}", 0.9), _out("c", "{}", 0.7)]
    picked = select(outs)
    assert picked is not None
    assert picked.expert_id == "b"


def test_select_ignores_schema_invalid_outputs_even_when_most_confident() -> None:
    outs = [_out("a", "{}", 0.2), _out("b", "{}", 0.99, valid=False)]
    picked = select(outs)
    assert picked is not None
    assert picked.expert_id == "a"


def test_select_returns_none_when_nothing_is_schema_valid() -> None:
    assert select([_out("a", "{}", 0.9, valid=False)]) is None


def test_select_breaks_confidence_ties_on_expert_id() -> None:
    outs = [_out("zeta", "{}", 0.5), _out("alpha", "{}", 0.5)]
    picked = select(outs)
    assert picked is not None
    assert picked.expert_id == "alpha"


def test_composite_recovers_every_fact_for_small_sets() -> None:
    outs = [
        _out("intent", '{"intent": "schedule"}', 0.67),
        _out("extractor", '{"dates": []}', 1.0),
        _out("third", '{"x": 1}', 0.0, valid=False),
    ]
    assert all(verify(composite_of(outs), outs).values())


@pytest.mark.parametrize("k", range(1, MAX_EXPERTS_PER_REQUEST + 1))
def test_provenance_recovers_for_every_allowed_count(k: int) -> None:
    rng = random.Random(1000 + k)
    outs = [
        _out(f"e{i}", f'{{"v": {rng.randrange(10_000)}}}', round(rng.random(), 2), rng.random() < 0.8)
        for i in range(k)
    ]
    result = aggregate(outs)
    assert result.provenance_ok, result.recovered


def test_provenance_holds_well_past_the_per_request_cap() -> None:
    # Measured separately: recovery is not the binding constraint at these sizes.
    rng = random.Random(64)
    outs = [_out(f"e{i}", f'{{"v": {rng.randrange(10_000)}}}', round(rng.random(), 2)) for i in range(32)]
    assert all(verify(composite_of(outs), outs).values())


def test_recovery_detects_a_payload_that_is_not_in_the_composite() -> None:
    outs = [_out("a", '{"v": 1}', 0.5), _out("b", '{"v": 2}', 0.5)]
    composite = composite_of(outs)
    tampered = [_out("a", '{"v": 999}', 0.5), _out("b", '{"v": 2}', 0.5)]
    recovered = verify(composite, tampered)
    assert recovered["a"] is False
    assert recovered["b"] is True


def test_aggregate_refuses_more_experts_than_the_cap() -> None:
    outs = [_out(f"e{i}", "{}", 0.5) for i in range(MAX_EXPERTS_PER_REQUEST + 1)]
    with pytest.raises(ValueError, match="per-request cap"):
        aggregate(outs)


def test_aggregate_returns_selection_and_provenance_together() -> None:
    outs = [_out("a", '{"v": 1}', 0.3), _out("b", '{"v": 2}', 0.8)]
    result = aggregate(outs)
    assert result.selected is not None
    assert result.selected.expert_id == "b"
    assert result.provenance_ok is True
    assert set(result.recovered) == {"a", "b"}
