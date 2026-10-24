"""Runnable F-extension J–O subset via harness scenarios."""
from harness.scenarios.v02_biological import SCENARIOS


def test_all_v02_scenarios_green():
    for sid, fn in SCENARIOS.items():
        fn()
