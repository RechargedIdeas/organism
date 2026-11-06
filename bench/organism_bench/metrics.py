"""Scores for routing predictions. Each takes the true labels and the predicted labels."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from organism_bench.dataset import EXPERTS, LABELS


def accuracy(truth: Sequence[str], pred: Sequence[str]) -> float:
    return float(np.mean([t == p for t, p in zip(truth, pred, strict=True)]))


def macro_f1(truth: Sequence[str], pred: Sequence[str]) -> float:
    scores: list[float] = []
    for label in LABELS:
        tp = sum(t == label and p == label for t, p in zip(truth, pred, strict=True))
        fp = sum(t != label and p == label for t, p in zip(truth, pred, strict=True))
        fn = sum(t == label and p != label for t, p in zip(truth, pred, strict=True))
        denominator = 2 * tp + fp + fn
        scores.append(2 * tp / denominator if denominator else 0.0)
    return float(np.mean(scores))


def recall(truth: Sequence[str], pred: Sequence[str], label: str) -> float:
    """Share of rows labelled `label` that are predicted as `label`. Zero when there are none."""
    hits = [p == label for t, p in zip(truth, pred, strict=True) if t == label]
    return float(np.mean(hits)) if hits else 0.0


def wrong_route_rate(truth: Sequence[str], pred: Sequence[str]) -> float:
    """Share of all rows sent to an expert other than the one the label names. An unsure row sent
    to any expert counts. This is the safety property the routing tests guard."""
    wrong = [p in EXPERTS and p != t for t, p in zip(truth, pred, strict=True)]
    return float(np.mean(wrong))


def summarise(truth: Sequence[str], pred: Sequence[str]) -> dict[str, float]:
    return {
        "accuracy": accuracy(truth, pred),
        "macro_f1": macro_f1(truth, pred),
        "wrong_route": wrong_route_rate(truth, pred),
        "recall_intent_classifier": recall(truth, pred, "intent_classifier"),
        "recall_extractor": recall(truth, pred, "extractor"),
        "recall_unsure": recall(truth, pred, "unsure"),
    }


def bootstrap_ci(
    correct: Sequence[bool], *, resamples: int = 1000, seed: int = 0
) -> tuple[float, float]:
    """95% percentile bootstrap interval for the mean of `correct`, resampling rows."""
    values = np.asarray(correct, dtype=np.float64)
    rng = np.random.default_rng(seed)
    means = np.array(
        [values[rng.integers(0, len(values), len(values))].mean() for _ in range(resamples)]
    )
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
