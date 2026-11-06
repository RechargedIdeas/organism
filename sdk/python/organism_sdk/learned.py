"""Learned classifier backend interface (gap D2).

A learned classifier is any object that maps a text to one logit per label. The interface does not care
how the model runs: an in-process network, a Rust binary behind a process boundary, or a stub in a test.
``decide_label`` turns the logits into a label or an abstention, using a calibrated abstention policy
from ``calibration.choose_threshold``. The policy decides, not the model: a backend cannot lower its own
threshold, and a malformed output abstains instead of raising.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from organism_sdk.calibration import AbstentionPolicy, softmax


@runtime_checkable
class LearnedBackend(Protocol):
    """A classifier. ``labels`` gives the output order; ``logits`` returns one raw score per label."""

    @property
    def labels(self) -> tuple[str, ...]: ...

    def logits(self, text: str) -> Sequence[float]: ...


@dataclass(frozen=True)
class ModelRef:
    """What identifies the weights that produced a decision. ``digest`` is the SHA-256 of the artifact."""

    name: str
    digest: str
    provenance: str = ""


@dataclass(frozen=True)
class LabelDecision:
    """One decision. ``label`` is ``None`` when the backend abstained; ``best_label`` is always its top guess."""

    label: str | None
    best_label: str | None
    probability: float
    abstained: bool
    reason: str
    model: ModelRef | None = None


def decide_label(
    backend: LearnedBackend,
    text: str,
    *,
    temperature: float,
    policy: AbstentionPolicy,
    model: ModelRef | None = None,
) -> LabelDecision:
    """Classify ``text`` and answer only when the calibrated probability clears the policy threshold.

    Fails closed: a backend that returns the wrong number of logits, a non-finite logit, or a non-positive
    temperature gives an abstention with a reason, not an answer.
    """
    labels = tuple(backend.labels)
    if len(labels) < 2:
        return _abstain("backend has fewer than two labels", None, 0.0, model)
    if not math.isfinite(temperature) or temperature <= 0:
        return _abstain("calibration temperature is invalid", None, 0.0, model)
    raw = list(backend.logits(text))
    if len(raw) != len(labels):
        return _abstain(f"backend returned {len(raw)} logits for {len(labels)} labels", None, 0.0, model)
    if not all(math.isfinite(x) for x in raw):
        return _abstain("backend returned a non-finite logit", None, 0.0, model)

    probs = softmax(raw, temperature)
    top = max(range(len(probs)), key=lambda i: (probs[i], -i))
    best, probability = labels[top], probs[top]
    if policy.answers(probability):
        return LabelDecision(
            label=best,
            best_label=best,
            probability=probability,
            abstained=False,
            reason=f"probability {probability:.3f} clears threshold {policy.threshold:.3f}",
            model=model,
        )
    return LabelDecision(
        label=None,
        best_label=best,
        probability=probability,
        abstained=True,
        reason=f"probability {probability:.3f} is below threshold {policy.threshold:.3f}",
        model=model,
    )


def _abstain(reason: str, best: str | None, probability: float, model: ModelRef | None) -> LabelDecision:
    return LabelDecision(
        label=None,
        best_label=best,
        probability=probability,
        abstained=True,
        reason=reason,
        model=model,
    )
