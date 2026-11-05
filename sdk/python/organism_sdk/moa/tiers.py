"""MoA degradation tiers T0 to T4 with recovery hysteresis (v1.11).

Tiers are chosen per request from expert health, the latency budget, GPU
availability, and the global degradation level. They are a different state
machine from ``DegradationMachine``, which tracks global levels L1 to L4 over
time. The global level enters here as one input: level L4 forces T4.

Tier semantics:

- T0 full: every active expert is healthy and within budget.
- T1 reduced: some active experts are unhealthy, and at least two are healthy.
- T2 single: one healthy expert. No aggregation. The schema check still applies.
- T3 CPU: an active expert needs a GPU and none is available. Those experts are
  skipped and the rest run on CPU.
- T4 deterministic: no healthy expert, or global level L4. A deterministic
  fallback answers.

Hysteresis: demotion (to a higher-numbered tier) takes effect immediately.
Promotion (to a lower-numbered tier) needs ``recover_after`` consecutive
observations of the better tier. This stops a flapping expert from toggling the
tier on every request.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class MoATier(IntEnum):
    T0 = 0
    T1 = 1
    T2 = 2
    T3 = 3
    T4 = 4


@dataclass(frozen=True)
class TierInputs:
    active: int
    healthy: int
    gpu_blocked: bool
    global_level: str = "L0"


@dataclass(frozen=True)
class TierDecision:
    tier: MoATier
    reason: str


def select_tier(inp: TierInputs) -> TierDecision:
    """The tier the current observation supports, with no hysteresis."""
    if inp.global_level == "L4":
        return TierDecision(MoATier.T4, "global_level_L4")
    if inp.active == 0 or inp.healthy == 0:
        return TierDecision(MoATier.T4, "no_healthy_expert")
    if inp.gpu_blocked:
        return TierDecision(MoATier.T3, "gpu_unavailable_cpu_path")
    if inp.healthy == inp.active:
        return TierDecision(MoATier.T0, "full_expert_set")
    if inp.healthy == 1:
        return TierDecision(MoATier.T2, "single_healthy_expert")
    return TierDecision(MoATier.T1, "reduced_expert_set")


class TierController:
    """Holds the current tier across requests, with recovery hysteresis."""

    def __init__(self, *, recover_after: int = 3) -> None:
        if recover_after < 1:
            raise ValueError("recover_after must be at least 1")
        self.recover_after = recover_after
        self._tier = MoATier.T0
        self._pending: MoATier | None = None
        self._streak = 0

    @property
    def tier(self) -> MoATier:
        return self._tier

    def observe(self, inp: TierInputs) -> TierDecision:
        proposed = select_tier(inp)

        if proposed.tier > self._tier:
            self._tier = proposed.tier
            self._clear_pending()
            return TierDecision(self._tier, f"demoted:{proposed.reason}")

        if proposed.tier == self._tier:
            self._clear_pending()
            return TierDecision(self._tier, f"held:{proposed.reason}")

        if self._pending == proposed.tier:
            self._streak += 1
        else:
            self._pending = proposed.tier
            self._streak = 1

        if self._streak >= self.recover_after:
            self._tier = proposed.tier
            self._clear_pending()
            return TierDecision(self._tier, f"promoted:{proposed.reason}")
        return TierDecision(self._tier, f"recovering:{self._streak}/{self.recover_after}:{proposed.reason}")

    def _clear_pending(self) -> None:
        self._pending = None
        self._streak = 0
