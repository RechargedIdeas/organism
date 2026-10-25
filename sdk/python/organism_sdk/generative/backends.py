"""Pluggable draft backends for generative code (template + LLM stub). CPU-only."""
from __future__ import annotations

import hashlib
import textwrap
from abc import ABC, abstractmethod
from typing import Any


class DraftBackend(ABC):
    name: str = "base"

    @abstractmethod
    def draft(self, intent: str, *, spec: dict[str, Any] | None = None) -> str:
        """Return Python source for a sandboxed ``main(**kwargs)`` entrypoint."""


class TemplateDraftBackend(DraftBackend):
    """Deterministic template backend — production-grade default, no network."""

    name = "template"

    def draft(self, intent: str, *, spec: dict[str, Any] | None = None) -> str:
        spec = spec or {}
        skill = str(spec.get("skill_name") or "skill")
        digest = hashlib.sha256(intent.encode()).hexdigest()[:12]
        safe_intent = intent[:200].replace("\n", " ").replace('"', "'")
        lines = [
            f"# Organism generative draft — backend=template digest={digest}",
            f"# intent: {safe_intent}",
            f"def main(x=0.0, y=0.0, **kwargs):",
            f'    """Generated Organism skill stub for {skill}."""',
            f"    a = float(x) + float(y)",
            f"    b = abs(a) * 0.5 + len({skill!r}) * 0.01",
            f"    return {{'ok': True, 'skill': {skill!r}, 'score': b, 'digest': {digest!r}}}",
            "",
        ]
        return "\n".join(lines)


class LLMStubBackend(DraftBackend):
    """Pluggable LLM-shaped stub — deterministic, offline, CPU-only.

    Production wiring can swap this for a real provider without changing the
    pipeline stages; promote gates remain mandatory either way.
    """

    name = "llm_stub"

    def draft(self, intent: str, *, spec: dict[str, Any] | None = None) -> str:
        spec = spec or {}
        skill = str(spec.get("skill_name") or "llm_skill")
        seed = int(hashlib.sha256(f"{intent}:{skill}".encode()).hexdigest()[:8], 16)
        bias = (seed % 1000) / 1000.0
        lines = [
            f"# Organism generative draft — backend=llm_stub seed={seed}",
            "def main(features=None, **kwargs):",
            "    features = list(features or [0.1, 0.2, 0.3])",
            f"    acc = {bias}",
            "    for i, v in enumerate(features):",
            "        acc = acc + float(v) * (0.1 + (i % 3) * 0.01)",
            f"    return {{'ok': True, 'skill': {skill!r}, 'prediction': acc, 'backend': 'llm_stub'}}",
            "",
        ]
        return "\n".join(lines)
