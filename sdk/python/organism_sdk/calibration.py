"""Calibration service for classifiers (gap D3).

Pure functions, shared by any learned expert that reports a probability. Three jobs:

- ``fit_temperature`` finds the single temperature that minimises the negative log-likelihood of the
  labels on held-out data. Temperature scaling keeps the ranking of the labels and changes only how
  confident the model is, so it cannot change which label wins.
- ``expected_calibration_error`` measures how far the stated confidence is from the observed accuracy,
  averaged over equal-width confidence bins.
- ``choose_threshold`` picks the abstention threshold: the lowest confidence at which answers still meet
  a target precision on the validation data, with enough answers to trust the estimate. It returns
  ``None`` when no threshold does, so the caller refuses to answer rather than guessing.

The validation data picks the threshold, so it must not be the test set. Isotonic calibration is not
implemented; only temperature scaling is.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

_TEMPERATURE_LOW = 0.05
_TEMPERATURE_HIGH = 20.0
_SEARCH_STEPS = 120


def softmax(logits: Sequence[float], temperature: float = 1.0) -> list[float]:
    """Numerically stable softmax of ``logits / temperature``. Raises on non-finite input."""
    if temperature <= 0 or not math.isfinite(temperature):
        raise ValueError("temperature must be a positive finite number")
    if not logits:
        raise ValueError("softmax needs at least one logit")
    scaled = [x / temperature for x in logits]
    if not all(math.isfinite(x) for x in scaled):
        raise ValueError("logits must be finite")
    top = max(scaled)
    exps = [math.exp(x - top) for x in scaled]
    total = sum(exps)
    return [e / total for e in exps]


def _nll(logit_rows: Sequence[Sequence[float]], labels: Sequence[int], temperature: float) -> float:
    total = 0.0
    for row, label in zip(logit_rows, labels, strict=True):
        probs = softmax(row, temperature)
        # A probability of exactly zero would give infinity; clamp to the smallest positive float.
        total -= math.log(max(probs[label], 1e-300))
    return total / len(labels)


def fit_temperature(logit_rows: Sequence[Sequence[float]], labels: Sequence[int]) -> float:
    """The temperature that minimises the mean negative log-likelihood on the given rows.

    A golden-section search over ``log(T)`` in ``[0.05, 20]``. The search is deterministic, so the same
    data gives the same temperature on every machine.
    """
    if not logit_rows or len(logit_rows) != len(labels):
        raise ValueError("need one label per logit row, and at least one row")
    width = len(logit_rows[0])
    if width < 2:
        raise ValueError("calibration needs at least two classes")
    for row, label in zip(logit_rows, labels, strict=True):
        if len(row) != width:
            raise ValueError("every logit row must have the same width")
        if not 0 <= label < width:
            raise ValueError("label index out of range")

    phi = (math.sqrt(5.0) - 1.0) / 2.0
    lo, hi = math.log(_TEMPERATURE_LOW), math.log(_TEMPERATURE_HIGH)
    a, b = hi - phi * (hi - lo), lo + phi * (hi - lo)
    fa = _nll(logit_rows, labels, math.exp(a))
    fb = _nll(logit_rows, labels, math.exp(b))
    for _ in range(_SEARCH_STEPS):
        if fa < fb:
            hi, b, fb = b, a, fa
            a = hi - phi * (hi - lo)
            fa = _nll(logit_rows, labels, math.exp(a))
        else:
            lo, a, fa = a, b, fb
            b = lo + phi * (hi - lo)
            fb = _nll(logit_rows, labels, math.exp(b))
        if hi - lo < 1e-9:
            break
    return math.exp((lo + hi) / 2.0)


def expected_calibration_error(probs: Sequence[float], correct: Sequence[bool], bins: int = 10) -> float:
    """Expected calibration error over ``bins`` equal-width confidence bins. Lower is better, 0 is perfect.

    ``probs`` holds each answer's confidence (its top probability) and ``correct`` says whether that
    answer was right.
    """
    if len(probs) != len(correct) or not probs:
        raise ValueError("need one correctness flag per confidence, and at least one")
    if bins < 1:
        raise ValueError("bins must be at least 1")
    counts = [0] * bins
    conf_sums = [0.0] * bins
    hit_sums = [0.0] * bins
    for p, ok in zip(probs, correct, strict=True):
        if not 0.0 <= p <= 1.0:
            raise ValueError("confidence must be in 0..1")
        index = min(int(p * bins), bins - 1)
        counts[index] += 1
        conf_sums[index] += p
        hit_sums[index] += 1.0 if ok else 0.0
    total = len(probs)
    ece = 0.0
    for n, conf_sum, hit_sum in zip(counts, conf_sums, hit_sums, strict=True):
        if n:
            ece += (n / total) * abs(hit_sum / n - conf_sum / n)
    return ece


@dataclass(frozen=True)
class AbstentionPolicy:
    """The threshold a learned expert must clear to answer, and what the validation data showed for it."""

    threshold: float
    target_precision: float
    precision: float  # precision on the validation data, of the answers given at this threshold
    coverage: float  # fraction of the validation items answered at this threshold
    support: int  # answers given on the validation data at this threshold

    def answers(self, confidence: float) -> bool:
        return confidence >= self.threshold


def choose_threshold(
    confidences: Sequence[float],
    correct: Sequence[bool],
    *,
    target_precision: float,
    min_support: int = 20,
) -> AbstentionPolicy | None:
    """The lowest threshold whose answers reach ``target_precision`` with at least ``min_support`` answers.

    The lowest such threshold gives the most coverage, so it is the one a product wants. ``None`` means no
    threshold on this data meets the target; the caller must then not answer on confidence alone.
    """
    if len(confidences) != len(correct) or not confidences:
        raise ValueError("need one correctness flag per confidence, and at least one")
    if not 0.0 < target_precision <= 1.0:
        raise ValueError("target_precision must be in (0, 1]")
    if min_support < 1:
        raise ValueError("min_support must be at least 1")
    total = len(confidences)
    pairs = sorted(zip(confidences, correct, strict=True), key=lambda pair: pair[0], reverse=True)
    best: AbstentionPolicy | None = None
    answered = 0
    hits = 0
    index = 0
    # Walk from the highest confidence down, so each step adds the next-lower confidence to the answers.
    while index < total:
        level = pairs[index][0]
        while index < total and pairs[index][0] == level:
            answered += 1
            hits += 1 if pairs[index][1] else 0
            index += 1
        precision = hits / answered
        if answered >= min_support and precision >= target_precision:
            best = AbstentionPolicy(
                threshold=level,
                target_precision=target_precision,
                precision=precision,
                coverage=answered / total,
                support=answered,
            )
    return best
