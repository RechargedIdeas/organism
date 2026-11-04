"""v1.11 MoA tiers: selection table and recovery hysteresis."""

from __future__ import annotations

import pytest
from organism_sdk.moa.tiers import MoATier, TierController, TierInputs, select_tier


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        (TierInputs(active=3, healthy=3, gpu_blocked=False), MoATier.T0),
        (TierInputs(active=1, healthy=1, gpu_blocked=False), MoATier.T0),
        (TierInputs(active=3, healthy=2, gpu_blocked=False), MoATier.T1),
        (TierInputs(active=3, healthy=1, gpu_blocked=False), MoATier.T2),
        (TierInputs(active=2, healthy=1, gpu_blocked=True), MoATier.T3),
        (TierInputs(active=3, healthy=0, gpu_blocked=False), MoATier.T4),
        (TierInputs(active=0, healthy=0, gpu_blocked=False), MoATier.T4),
        (TierInputs(active=3, healthy=3, gpu_blocked=False, global_level="L4"), MoATier.T4),
    ],
)
def test_select_tier_table(inp, expected):
    assert select_tier(inp).tier == expected


def test_single_active_expert_that_is_healthy_is_full_not_degraded() -> None:
    # A query that only one expert is relevant to is not a degradation.
    assert select_tier(TierInputs(active=1, healthy=1, gpu_blocked=False)).tier == MoATier.T0


def test_demotion_is_immediate() -> None:
    controller = TierController(recover_after=3)
    decision = controller.observe(TierInputs(active=3, healthy=1, gpu_blocked=False))
    assert decision.tier == MoATier.T2
    assert decision.reason.startswith("demoted:")


def test_promotion_needs_consecutive_healthy_observations() -> None:
    controller = TierController(recover_after=3)
    controller.observe(TierInputs(active=3, healthy=0, gpu_blocked=False))
    healthy = TierInputs(active=3, healthy=3, gpu_blocked=False)
    assert controller.observe(healthy).reason.startswith("recovering:1/3")
    assert controller.observe(healthy).reason.startswith("recovering:2/3")
    decision = controller.observe(healthy)
    assert decision.tier == MoATier.T0
    assert decision.reason.startswith("promoted:")


def test_flapping_expert_does_not_toggle_the_tier() -> None:
    controller = TierController(recover_after=3)
    controller.observe(TierInputs(active=3, healthy=1, gpu_blocked=False))
    healthy = TierInputs(active=3, healthy=3, gpu_blocked=False)
    degraded = TierInputs(active=3, healthy=1, gpu_blocked=False)
    tiers = []
    for _ in range(4):
        tiers.append(controller.observe(healthy).tier)
        tiers.append(controller.observe(degraded).tier)
    assert set(tiers) == {MoATier.T2}


def test_an_observation_at_the_current_tier_resets_the_recovery_streak() -> None:
    controller = TierController(recover_after=3)
    controller.observe(TierInputs(active=3, healthy=1, gpu_blocked=False))  # T2
    healthy = TierInputs(active=3, healthy=3, gpu_blocked=False)
    controller.observe(healthy)
    controller.observe(healthy)
    controller.observe(TierInputs(active=3, healthy=1, gpu_blocked=False))  # back at T2
    assert controller.observe(healthy).reason.startswith("recovering:1/3")
    assert controller.tier == MoATier.T2


def test_a_different_recovery_target_restarts_the_streak() -> None:
    controller = TierController(recover_after=3)
    controller.observe(TierInputs(active=3, healthy=1, gpu_blocked=False))  # T2
    controller.observe(TierInputs(active=3, healthy=3, gpu_blocked=False))  # toward T0, 1/3
    controller.observe(TierInputs(active=3, healthy=3, gpu_blocked=False))  # toward T0, 2/3
    decision = controller.observe(TierInputs(active=3, healthy=2, gpu_blocked=False))  # toward T1
    assert decision.reason.startswith("recovering:1/3")
    assert controller.tier == MoATier.T2


def test_recover_after_must_be_positive() -> None:
    with pytest.raises(ValueError, match="recover_after"):
        TierController(recover_after=0)


def test_global_level_l4_is_forced_immediately_and_held_until_recovery() -> None:
    controller = TierController(recover_after=2)
    assert controller.observe(TierInputs(3, 3, False, global_level="L4")).tier == MoATier.T4
    assert controller.observe(TierInputs(3, 3, False, global_level="L0")).tier == MoATier.T4
    assert controller.observe(TierInputs(3, 3, False, global_level="L0")).tier == MoATier.T0
