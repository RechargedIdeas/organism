"""The labeled routing set the probes are trained and scored on."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from organism_bench.specs import DATASET

LABELS: tuple[str, ...] = ("intent_classifier", "extractor", "unsure")
EXPERTS: tuple[str, ...] = ("intent_classifier", "extractor")


@dataclass(frozen=True)
class Row:
    id: str
    query: str
    label: str
    source: str


def load(path: Path = DATASET) -> list[Row]:
    rows = [
        Row(entry["id"], entry["query"], entry["label"], entry["source"])
        for entry in json.loads(path.read_text(encoding="utf-8"))
    ]
    unknown = {row.label for row in rows} - set(LABELS)
    if unknown:
        raise ValueError(f"unknown labels in {path}: {sorted(unknown)}")
    return rows


def stratified_folds(labels: np.ndarray, folds: int, seed: int) -> np.ndarray:
    """Assign each row a fold, spreading every label evenly across the folds."""
    rng = np.random.default_rng(seed)
    assignment = np.empty(len(labels), dtype=np.int64)
    for label in LABELS:
        index = np.flatnonzero(labels == label)
        rng.shuffle(index)
        assignment[index] = np.arange(len(index)) % folds
    return assignment
