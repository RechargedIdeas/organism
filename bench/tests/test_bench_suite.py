"""Tests for the encoder benchmark.

They use the deterministic hash encoder, so they need no downloaded weights and run in the normal
test suite. The real encoders are exercised by bench/run_bench.py, not here.
"""

from __future__ import annotations

import numpy as np
from organism_bench import adapters, dataset, measure, metrics
from organism_bench.probe import LinearProbe
from organism_bench.specs import DATASET, ModelSpec, load_models


def test_model_registry_is_well_formed() -> None:
    specs = load_models()
    assert specs
    assert {spec.kind for spec in specs} <= {"sentence", "static"}


def test_committed_dataset_has_three_labels_and_no_duplicate_queries() -> None:
    rows = dataset.load(DATASET)
    assert {row.label for row in rows} == set(dataset.LABELS)
    keys = [" ".join(row.query.split()).lower() for row in rows]
    assert len(keys) == len(set(keys))


def test_stratified_folds_spread_every_label_and_are_deterministic() -> None:
    labels = np.array(["extractor"] * 10 + ["unsure"] * 10 + ["intent_classifier"] * 10)
    first = dataset.stratified_folds(labels, 5, seed=1)
    again = dataset.stratified_folds(labels, 5, seed=1)
    assert np.array_equal(first, again)
    for fold in range(5):
        assert set(labels[first == fold]) == set(dataset.LABELS)


def test_metrics_on_a_known_example() -> None:
    truth = ["extractor", "extractor", "unsure", "intent_classifier"]
    pred = ["extractor", "intent_classifier", "extractor", "intent_classifier"]
    assert metrics.accuracy(truth, pred) == 0.5
    assert metrics.recall(truth, pred, "extractor") == 0.5
    # Two rows went to an expert the label does not name: an extractor row sent to the intent
    # expert, and an unsure row sent to the extractor.
    assert metrics.wrong_route_rate(truth, pred) == 0.5
    assert metrics.macro_f1(truth, truth) == 1.0


def test_linear_probe_separates_two_clusters_and_is_deterministic() -> None:
    rng = np.random.default_rng(0)
    a = rng.normal(0.0, 0.1, (30, 8)) + 3.0
    b = rng.normal(0.0, 0.1, (30, 8)) - 3.0
    features = np.vstack([a, b])
    labels = ["extractor"] * 30 + ["unsure"] * 30
    first = LinearProbe(("extractor", "unsure")).fit(features, labels)
    second = LinearProbe(("extractor", "unsure")).fit(features, labels)
    assert first.predict(features) == labels
    assert first.predict(features) == second.predict(features)
    assert first.parameters == 8 * 2 + 2


def test_hash_encoder_is_deterministic_and_unit_length() -> None:
    encoder = adapters.HashEncoder(dim=32)
    vectors = encoder.encode(
        ["Pull the email addresses out of this", "Pull the email addresses out of this"]
    )
    assert vectors.shape == (2, 32)
    assert np.allclose(vectors[0], vectors[1])
    assert np.isclose(np.linalg.norm(vectors[0]), 1.0)


def test_lexical_control_routes_an_extraction_and_leaves_a_negative_unsure() -> None:
    rows = [
        dataset.Row("a", "Pull the email addresses out of this list: ann@a.io", "extractor", "t"),
        dataset.Row(
            "b", "Which email addresses are allowed to post to the all-staff list?", "unsure", "t"
        ),
    ]
    assert measure.lexical_predictions(rows) == ["extractor", "unsure"]


def test_measure_one_end_to_end_with_the_hash_encoder() -> None:
    spec = ModelSpec("hash-smoke", "local/hash", "hash")
    result = measure.measure_one(spec, folds=5, seeds=2, threads=1)
    assert result["rows"] == len(dataset.load(DATASET))
    assert result["dim"] == adapters.HashEncoder().dim
    for key in ("accuracy", "macro_f1", "wrong_route"):
        assert 0.0 <= result["scores"][key]["mean"] <= 1.0
    assert result["latency_ms"]["p50"] >= 0.0
