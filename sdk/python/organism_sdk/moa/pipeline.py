"""MoA pipeline: capability routing, tier selection, and aggregation for one query (v1.11).

Per query:

1. Stage 1: keep experts that serve the requested form. With no form, keep all.
2. Stage 2: the capability scorer returns ``expert``, ``unsure``, or ``llm_fallback``.
   ``unsure`` and ``llm_fallback`` end the request with no answer.
3. Take the top-k experts that show keyword evidence as the active set.
4. Health: an active expert is healthy if its health report is HEALTHY, it is
   within the latency budget, and its GPU need (if any) can be met. Failed experts
   stay in the active set and count against the healthy total. That is how a
   failure shows up as a tier change.
5. The tier controller picks the tier, with hysteresis. The executed path follows
   that tier:
   - T4: deterministic fallback.
   - T2: run the top healthy expert alone. No aggregation.
   - T0, T1, T3: run all healthy experts and aggregate.
   A result that fails the schema check on every path falls back to T4.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from organism_sdk.moa.aggregate import MAX_EXPERTS_PER_REQUEST, aggregate
from organism_sdk.moa.experts import HEALTHY, Expert, ExpertOutput
from organism_sdk.moa.scorer import ROUTE_EXPERT, CapabilityScorer, LexicalScorer
from organism_sdk.moa.tiers import MoATier, TierController, TierInputs

ROUTE_DETERMINISTIC = "deterministic"
DETERMINISTIC_ID = "deterministic_fallback"

DeterministicFallback = Callable[[str, str | None], ExpertOutput]


def default_deterministic_fallback(query: str, form: str | None) -> ExpertOutput:
    """Answers nothing, with a reason. Replace with a real deterministic module."""
    payload = json.dumps({"answer": None, "reason": "no_healthy_expert"}, sort_keys=True)
    return ExpertOutput(DETERMINISTIC_ID, payload, 0.0, schema_valid=True)


@dataclass(frozen=True)
class MoAResult:
    route: str
    tier: MoATier | None
    expert_id: str | None
    payload: str | None
    confidence: float | None
    reason: str
    active: tuple[str, ...] = ()
    ran: tuple[str, ...] = ()
    provenance_ok: bool | None = None


class MoAPipeline:
    def __init__(
        self,
        experts: Iterable[Expert],
        *,
        scorer: CapabilityScorer | None = None,
        controller: TierController | None = None,
        top_k: int = 3,
        latency_budget_ms: float = 50.0,
        gpu_available: bool = False,
        deterministic_fallback: DeterministicFallback = default_deterministic_fallback,
    ) -> None:
        if not 1 <= top_k <= MAX_EXPERTS_PER_REQUEST:
            raise ValueError(f"top_k must be between 1 and {MAX_EXPERTS_PER_REQUEST}")
        self._experts: dict[str, Expert] = {}
        for e in experts:
            eid = e.descriptor.expert_id
            if eid in self._experts:
                raise ValueError(f"duplicate expert id {eid!r}")
            self._experts[eid] = e
        self._scorer = scorer or LexicalScorer()
        self._controller = controller or TierController()
        self._top_k = top_k
        self._latency_budget_ms = latency_budget_ms
        self._gpu_available = gpu_available
        self._deterministic = deterministic_fallback

    @property
    def tier(self) -> MoATier:
        return self._controller.tier

    def run(self, query: str, *, form: str | None = None, global_level: str = "L0") -> MoAResult:
        candidates = [e for e in self._experts.values() if form is None or form in e.descriptor.task_forms]
        decision = self._scorer.decide(query, candidates)
        if decision.route != ROUTE_EXPERT:
            return MoAResult(decision.route, None, None, None, None, decision.reason)

        active = [s.expert_id for s in decision.ranked if s.score > 0.0][: self._top_k]
        healthy, gpu_blocked = self._healthy(active)
        observed = self._controller.observe(
            TierInputs(active=len(active), healthy=len(healthy), gpu_blocked=gpu_blocked, global_level=global_level)
        )
        tier = observed.tier

        if tier == MoATier.T4:
            return self._deterministic_result(query, form, observed.reason, active)

        run = healthy[:1] if tier == MoATier.T2 else healthy
        outputs = [self._experts[eid].answer(query, form) for eid in run]

        if tier == MoATier.T2:
            only = outputs[0]
            if not only.schema_valid:
                return self._deterministic_result(query, form, "no_valid_output", active)
            return MoAResult(
                ROUTE_EXPERT, tier, only.expert_id, only.payload, only.confidence,
                observed.reason, tuple(active), tuple(run), None,
            )

        agg = aggregate(outputs)
        if agg.selected is None:
            return self._deterministic_result(query, form, "no_valid_output", active)
        return MoAResult(
            ROUTE_EXPERT, tier, agg.selected.expert_id, agg.selected.payload, agg.selected.confidence,
            observed.reason, tuple(active), tuple(run), agg.provenance_ok,
        )

    def _healthy(self, active: list[str]) -> tuple[list[str], bool]:
        healthy: list[str] = []
        gpu_blocked = False
        for eid in active:
            expert = self._experts[eid]
            d = expert.descriptor
            if d.requires_gpu and not self._gpu_available:
                gpu_blocked = True
                continue
            if expert.health().status != HEALTHY:
                continue
            if d.expected_latency_ms > self._latency_budget_ms:
                continue
            healthy.append(eid)
        return healthy, gpu_blocked

    def _deterministic_result(self, query: str, form: str | None, reason: str, active: list[str]) -> MoAResult:
        out = self._deterministic(query, form)
        return MoAResult(
            ROUTE_DETERMINISTIC, MoATier.T4, out.expert_id, out.payload, out.confidence,
            reason, tuple(active), (), None,
        )
