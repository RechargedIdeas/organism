"""Where the benchmark finds its model registry, lock file, weights and dataset."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BENCH = Path(__file__).resolve().parents[1]
MODELS_TOML = BENCH / "models.toml"
LOCK = BENCH / "models.lock.json"
MODELS_DIR = BENCH / "models"
DATASET = BENCH / "data" / "intent_routing.json"
KINDS = frozenset({"sentence", "static", "hash"})


@dataclass(frozen=True)
class ModelSpec:
    name: str
    repo: str
    kind: str
    query_prefix: str = ""

    @property
    def path(self) -> Path:
        return MODELS_DIR / self.name


def load_models() -> list[ModelSpec]:
    data = tomllib.loads(MODELS_TOML.read_text(encoding="utf-8"))
    specs = [
        ModelSpec(entry["name"], entry["repo"], entry["kind"], entry.get("query_prefix", ""))
        for entry in data["model"]
    ]
    names = [spec.name for spec in specs]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate model names in {MODELS_TOML}")
    unknown = {spec.kind for spec in specs} - KINDS
    if unknown:
        raise ValueError(f"unknown model kinds in {MODELS_TOML}: {sorted(unknown)}")
    return specs


def find_model(name: str) -> ModelSpec:
    for spec in load_models():
        if spec.name == name:
            return spec
    raise KeyError(f"no model named {name!r} in {MODELS_TOML}")


def load_lock() -> dict[str, dict[str, Any]]:
    if not LOCK.exists():
        return {}
    lock: dict[str, dict[str, Any]] = json.loads(LOCK.read_text(encoding="utf-8"))
    return lock
