"""Neuromorphic simulator backend (v1.0-E) — RESEARCH_SIM.

When ``ORGANISM_NEURO_SIM=1``, treat neuromorphic capability as present so the
SNN sentinel wake path may dispatch as if HW were available. Default remains
gated off. Not real silicon.
"""
from __future__ import annotations

import os
from typing import Iterable


def neuro_sim_enabled() -> bool:
    return os.environ.get("ORGANISM_NEURO_SIM", "").strip() in {"1", "true", "TRUE", "yes"}


def hardware_caps_with_sim(base: Iterable[str] | None = None) -> set[str]:
    caps = set(base or {"NONE"})
    caps.add("NONE")
    if neuro_sim_enabled():
        caps.add("NEUROMORPHIC")
    return caps


RESEARCH_SIM = "RESEARCH_SIM"  # STATUS marker for faithful software simulators
