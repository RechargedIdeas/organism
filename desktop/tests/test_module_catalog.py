"""Module catalog + one-click register + RESEARCH_TIER badges."""
from __future__ import annotations

from organism_desktop.service import DesktopService


def test_catalog_lists_substrates_with_research_badges():
    svc = DesktopService.create()
    cat = svc.module_catalog()
    assert len(cat) >= 8
    ids = {c["catalog_id"] for c in cat}
    assert "deterministic_engine" in ids
    assert "physical_research" in ids
    assert "snn_sentinel" in ids
    research = [c for c in cat if c["research_tier"]]
    assert research
    assert all(c.get("research_badge") == "RESEARCH_TIER" for c in research)
    assert all(c["may_actuate_declared"] is False for c in research)


def test_register_catalog_hdc():
    svc = DesktopService.create()
    # Ensure not already confusing state
    result = svc.register_catalog_module("hdc_module")
    assert result["registered"] is True
    assert result["module_id"] == "hdc_module"
    assert result["may_actuate"] is False
    assert any(m["module_id"] == "hdc_module" for m in svc.list_modules())
    # Catalog marks registered
    entry = next(c for c in svc.module_catalog() if c["catalog_id"] == "hdc_module")
    assert entry["registered"] is True


def test_register_research_tier_physical():
    svc = DesktopService.create()
    result = svc.register_catalog_module("physical_research")
    assert result["registered"] is True
    assert result["research_tier"] is True
    assert result["research_badge"] == "RESEARCH_TIER"
    assert result["may_actuate"] is False
