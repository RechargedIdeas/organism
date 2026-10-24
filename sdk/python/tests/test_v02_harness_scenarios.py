"""Runnable F-extension J–O full matrix via harness scenarios."""
from harness.scenarios.v02_biological import SCENARIOS

MATRIX_IDS = [
    "J1", "J2", "J3", "J4",
    "K1", "K2", "K3", "K4", "K5", "K6",
    "L1", "L2", "L3", "L4", "L5", "L6",
    "M1", "M2", "M3", "M4",
    "N1", "N2", "N3", "N4", "N5",
    "O1", "O2", "O3", "O4", "O5",
]
STUB_IDS = ["LEARNED_ISE", "FED_OXYTOCIN", "MIRROR_LAG_OOS", "METAMODEL_OOS"]


def test_all_matrix_ids_registered():
    for sid in MATRIX_IDS + STUB_IDS:
        assert sid in SCENARIOS, f"missing scenario {sid}"


def test_all_v02_scenarios_green():
    for sid in MATRIX_IDS + STUB_IDS:
        SCENARIOS[sid]()


def test_each_matrix_id_individually():
    """Param-style loop so a single failure names the ID clearly."""
    failures = []
    for sid in MATRIX_IDS + STUB_IDS:
        try:
            SCENARIOS[sid]()
        except Exception as exc:  # noqa: BLE001 — collect all
            failures.append(f"{sid}: {exc}")
    assert not failures, "\n".join(failures)
