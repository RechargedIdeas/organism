"""v0.3-M4 — thin import smoke (full tests live under modules/snn_sentinel/tests)."""
from snn_sentinel import SNNSentinel, MODULE_ID


def test_snn_module_importable():
    s = SNNSentinel()
    c = s.declare_contract()
    assert c.identity.module_id == MODULE_ID
    assert c.metabolic.requires_special_hardware.value == "NEUROMORPHIC"
