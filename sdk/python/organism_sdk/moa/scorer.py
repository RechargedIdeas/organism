"""Capability scorer: routes a query to experts by descriptor match (v1.11).

Stage 2 of the MoA router. Stage 1 (form filtering) happens in the pipeline.
The scorer returns one of three routes:

- ``expert``: one expert clears ``min_score`` and leads the runner-up by ``min_margin``.
- ``unsure``: no expert clears ``min_score``, or the top two are too close to call.
- ``llm_fallback``: no expert clears ``min_score`` and fallback is enabled. The
  hosted LLM stays off by default (decision D3 in the upgrade plan).

The default ``LexicalScorer`` counts matched descriptor keywords. A score saturates
at ``saturation`` matches so that a long keyword list is not penalized. A learned
encoder can replace it behind the same ``CapabilityScorer`` protocol.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from organism_sdk.moa.experts import CapabilityDescriptor, Expert

ROUTE_EXPERT = "expert"
ROUTE_UNSURE = "unsure"
ROUTE_LLM_FALLBACK = "llm_fallback"


@dataclass(frozen=True)
class ScoredExpert:
    expert_id: str
    score: float
    matched: tuple[str, ...]


@dataclass(frozen=True)
class RouteDecision:
    route: str
    expert_id: str | None
    ranked: tuple[ScoredExpert, ...]
    margin: float
    reason: str


class CapabilityScorer(Protocol):
    def decide(self, query: str, experts: Iterable[Expert]) -> RouteDecision: ...


def _contains(text: str, phrase: str) -> bool:
    return re.search(r"\b" + re.escape(phrase) + r"\b", text) is not None


class LexicalScorer:
    def __init__(
        self,
        *,
        min_score: float = 0.5,
        min_margin: float = 0.25,
        saturation: int = 2,
        allow_llm_fallback: bool = False,
    ) -> None:
        if saturation < 1:
            raise ValueError("saturation must be at least 1")
        self.min_score = min_score
        self.min_margin = min_margin
        self.saturation = saturation
        self.allow_llm_fallback = allow_llm_fallback

    def rank(self, query: str, descriptors: Iterable[CapabilityDescriptor]) -> tuple[ScoredExpert, ...]:
        text = query.lower()
        scored = []
        for d in descriptors:
            matched = tuple(kw for kw in d.keywords if _contains(text, kw))
            score = min(1.0, len(matched) / self.saturation)
            scored.append(ScoredExpert(d.expert_id, score, matched))
        scored.sort(key=lambda s: (-s.score, s.expert_id))
        return tuple(scored)

    def decide(self, query: str, experts: Iterable[Expert]) -> RouteDecision:
        descriptors = [e.descriptor for e in experts]
        if not descriptors:
            return RouteDecision(ROUTE_UNSURE, None, (), 0.0, "no_candidates")
        ranked = self.rank(query, descriptors)
        top = ranked[0]
        runner_up = ranked[1].score if len(ranked) > 1 else 0.0
        margin = top.score - runner_up

        if top.score < self.min_score:
            route = ROUTE_LLM_FALLBACK if self.allow_llm_fallback else ROUTE_UNSURE
            return RouteDecision(route, None, ranked, margin, "no_expert_clears_min_score")
        if margin < self.min_margin:
            return RouteDecision(ROUTE_UNSURE, None, ranked, margin, "ambiguous_top_two")
        return RouteDecision(ROUTE_EXPERT, top.expert_id, ranked, margin, "clear_leader")
