"""Measure one encoder, and the controls that need no encoder.

For an encoder: load cost, memory, per-query latency, batch throughput, and probe scores from
stratified cross-validation repeated over several seeds. For the controls: a majority-class
baseline and the lexical router that ships in organism_sdk.
"""

from __future__ import annotations

import os
import platform
import sys
import time
from collections import Counter
from collections.abc import Sequence
from typing import Any

import numpy as np

from organism_bench import adapters, dataset, metrics
from organism_bench.probe import LinearProbe
from organism_bench.specs import DATASET, ModelSpec, load_lock

MB = 1024 * 1024


def _rss() -> int:
    """Resident memory of this process in bytes, or 0 when psutil is not installed."""
    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError:
        return 0
    return int(psutil.Process().memory_info().rss)


def _set_threads(threads: int) -> None:
    if "torch" in sys.modules:
        import torch

        torch.set_num_threads(threads)


def _host() -> dict[str, Any]:
    info: dict[str, Any] = {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
    }
    if "torch" in sys.modules:
        import torch

        info["torch"] = torch.__version__
        info["torch_threads"] = torch.get_num_threads()
    return info


def _aggregate(per_seed: Sequence[dict[str, float]]) -> dict[str, dict[str, float]]:
    return {
        key: {
            "mean": float(np.mean([scores[key] for scores in per_seed])),
            "std": float(np.std([scores[key] for scores in per_seed])),
        }
        for key in per_seed[0]
    }


def _cross_validate(
    embeddings: np.ndarray, labels: np.ndarray, *, folds: int, seeds: int
) -> tuple[list[dict[str, float]], list[bool]]:
    per_seed: list[dict[str, float]] = []
    first_correct: list[bool] = []
    for seed in range(seeds):
        assignment = dataset.stratified_folds(labels, folds, seed)
        guess = np.empty(len(labels), dtype=object)
        for fold in range(folds):
            test = assignment == fold
            probe = LinearProbe(dataset.LABELS).fit(embeddings[~test], labels[~test].tolist())
            guess[test] = probe.predict(embeddings[test])
        truth = labels.tolist()
        predicted = guess.tolist()
        per_seed.append(metrics.summarise(truth, predicted))
        if seed == 0:
            first_correct = [t == p for t, p in zip(truth, predicted, strict=True)]
    return per_seed, first_correct


def measure_one(spec: ModelSpec, *, folds: int, seeds: int, threads: int) -> dict[str, Any]:
    rows = dataset.load(DATASET)
    texts = [row.query for row in rows]
    labels = np.asarray([row.label for row in rows])
    lock_entry = load_lock().get(spec.name, {})

    samples = [_rss()]
    start = time.perf_counter()
    encoder = adapters.load_encoder(spec)
    load_s = time.perf_counter() - start
    _set_threads(threads)
    samples.append(_rss())

    for text in texts[:5]:
        encoder.encode([text])
    single_ms: list[float] = []
    for text in texts:
        start = time.perf_counter()
        encoder.encode([text])
        single_ms.append((time.perf_counter() - start) * 1000.0)
    start = time.perf_counter()
    embeddings = encoder.encode(texts)
    batch_s = time.perf_counter() - start
    samples.append(_rss())

    per_seed, first_correct = _cross_validate(embeddings, labels, folds=folds, seeds=seeds)
    ci_low, ci_high = metrics.bootstrap_ci(first_correct)
    latency = np.asarray(single_ms)
    return {
        "name": spec.name,
        "repo": spec.repo,
        "revision": lock_entry.get("revision", "unlocked"),
        "license": lock_entry.get("license", "unknown"),
        "kind": spec.kind,
        "dim": int(embeddings.shape[1]),
        "params": int(encoder.params),
        "probe_parameters": int(embeddings.shape[1] * len(dataset.LABELS) + len(dataset.LABELS)),
        "load_s": round(load_s, 3),
        "peak_rss_mb": round(max(samples) / MB, 1),
        "latency_ms": {
            "p50": round(float(np.percentile(latency, 50)), 3),
            "p95": round(float(np.percentile(latency, 95)), 3),
            "max": round(float(latency.max()), 3),
        },
        "batch_rows_per_s": round(len(texts) / batch_s, 1),
        "rows": len(texts),
        "folds": folds,
        "seeds": seeds,
        "scores": _aggregate(per_seed),
        "accuracy_ci95_seed0": [round(ci_low, 4), round(ci_high, 4)],
        "host": _host(),
    }


def lexical_predictions(rows: Sequence[dataset.Row]) -> list[str]:
    """The shipped lexical router: its expert id when it routes, otherwise unsure."""
    from organism_sdk.moa.reference import reference_experts
    from organism_sdk.moa.scorer import ROUTE_EXPERT, LexicalScorer

    scorer = LexicalScorer()
    experts = reference_experts()
    predictions: list[str] = []
    for row in rows:
        decision = scorer.decide(row.query, experts)
        routed = decision.expert_id if decision.route == ROUTE_EXPERT else None
        predictions.append(routed or "unsure")
    return predictions


def _majority_scores(labels: np.ndarray, *, folds: int, seeds: int) -> dict[str, dict[str, float]]:
    per_seed: list[dict[str, float]] = []
    for seed in range(seeds):
        assignment = dataset.stratified_folds(labels, folds, seed)
        guess: list[str] = [""] * len(labels)
        for fold in range(folds):
            test = assignment == fold
            top = Counter(labels[~test].tolist()).most_common(1)[0][0]
            for index in np.flatnonzero(test):
                guess[int(index)] = top
        per_seed.append(metrics.summarise(labels.tolist(), guess))
    return _aggregate(per_seed)


def controls(*, folds: int, seeds: int) -> dict[str, Any]:
    rows = dataset.load(DATASET)
    labels = np.asarray([row.label for row in rows])
    lexical = metrics.summarise(labels.tolist(), lexical_predictions(rows))
    return {
        "majority_class": _majority_scores(labels, folds=folds, seeds=seeds),
        "lexical_router": {key: {"mean": value, "std": 0.0} for key, value in lexical.items()},
        "lexical_router_note": "Rules were tuned on these rows, so this score is optimistic.",
        "rows": len(rows),
    }
