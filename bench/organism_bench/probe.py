"""The trained head the benchmark puts on each encoder.

A multinomial logistic regression on frozen, standardised embeddings. It is fitted by full-batch
gradient descent from a zero start, so a fit is deterministic and needs no random seed. The step
size comes from the curvature bound of the cross-entropy loss, so the descent cannot diverge.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def _softmax(scores: np.ndarray) -> np.ndarray:
    shifted = scores - scores.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return np.asarray(exp / exp.sum(axis=1, keepdims=True), dtype=np.float64)


class LinearProbe:
    def __init__(self, classes: Sequence[str], *, l2: float = 1e-2, steps: int = 400) -> None:
        self.classes = tuple(classes)
        self.l2 = l2
        self.steps = steps
        self._mu = np.zeros(0)
        self._sigma = np.ones(0)
        self._weights = np.zeros((0, 0))
        self._bias = np.zeros(0)

    @property
    def parameters(self) -> int:
        return int(self._weights.size + self._bias.size)

    def fit(self, features: np.ndarray, labels: Sequence[str]) -> LinearProbe:
        self._mu = features.mean(axis=0)
        self._sigma = features.std(axis=0) + 1e-6
        x = (features - self._mu) / self._sigma
        n, dim = x.shape
        index = {label: i for i, label in enumerate(self.classes)}
        target = np.zeros((n, len(self.classes)))
        target[np.arange(n), [index[label] for label in labels]] = 1.0
        # The cross-entropy Hessian is bounded by 0.5 * X^T X / n, so 1 / L is a safe step.
        curvature = 0.5 * float(np.linalg.norm(x, 2)) ** 2 / n + self.l2
        step = 1.0 / curvature
        weights = np.zeros((dim, len(self.classes)))
        bias = np.zeros(len(self.classes))
        for _ in range(self.steps):
            grad = (_softmax(x @ weights + bias) - target) / n
            weights -= step * (x.T @ grad + self.l2 * weights)
            bias -= step * grad.sum(axis=0)
        self._weights = weights
        self._bias = bias
        return self

    def predict(self, features: np.ndarray) -> list[str]:
        x = (features - self._mu) / self._sigma
        scores = x @ self._weights + self._bias
        return [self.classes[i] for i in scores.argmax(axis=1)]
