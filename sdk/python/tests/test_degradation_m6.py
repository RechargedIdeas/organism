"""M6: B.6 matrix subset + no-flapping assertion."""
from harness.scenarios.m6_faults import (
    scenario_byzantine_to_l4,
    scenario_kill_learned_l0_to_l1,
    scenario_no_flapping_on_restore,
    scenario_persistent_failure_l1_to_l2,
    scenario_trace_corrupt_to_l4,
)


def test_b6_kill_learned_l0_l1():
    scenario_kill_learned_l0_to_l1()


def test_b6_persistent_failure_l1_l2():
    scenario_persistent_failure_l1_to_l2()


def test_b6_no_flapping():
    scenario_no_flapping_on_restore()


def test_b6_trace_corrupt_l4():
    scenario_trace_corrupt_to_l4()


def test_b6_byzantine_l4():
    scenario_byzantine_to_l4()
