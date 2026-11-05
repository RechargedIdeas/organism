"""v0.3-M4 — thin import smoke (full tests live under modules/snn_sentinel/tests)."""
from snn_sentinel import MODULE_ID, SNNSentinel


def test_snn_module_importable() -> None:
    s = SNNSentinel()
    c = s.declare_contract()
    assert c.identity.module_id == MODULE_ID
    assert c.metabolic.requires_special_hardware.value == "NEUROMORPHIC"
