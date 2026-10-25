"""Neuromorphic simulator backend — RESEARCH_SIM on CPU (v1.0-E / v1.3).

When ``ORGANISM_NEURO_SIM=1``, treat neuromorphic capability as present so the
SNN sentinel wake path may dispatch as if HW were available. The spike-rate
simulator itself **always** runs on ``CPU_GENERAL`` and never requires silicon.

Product guarantee: missing neuromorphic / GPU / NPU never hard-fails the
process. See ``docs/CPU_EVERYWHERE.md``.
"""
from __future__ import annotations

import os
from typing import Iterable

from organism_sdk.device import RuntimeId, select_compute_backend


def neuro_sim_enabled() -> bool:
    return os.environ.get("ORGANISM_NEURO_SIM", "").strip() in {"1", "true", "TRUE", "yes"}


def hardware_caps_with_sim(base: Iterable[str] | None = None) -> set[str]:
    caps = set(base or {"NONE"})
    caps.add("NONE")
    if neuro_sim_enabled():
        caps.add("NEUROMORPHIC")
    return caps


def neuromorphic_cpu_backend():
    """Always-available CPU RESEARCH_SIM selection for SNN / neuro workloads."""
    return select_compute_backend(prefer=RuntimeId.NEUROMORPHIC)


RESEARCH_SIM = "RESEARCH_SIM"  # STATUS marker for faithful software simulators
CPU_RESEARCH_SIM_BACKEND = "research_sim_cpu"
