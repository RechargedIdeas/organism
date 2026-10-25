"""Hormone timeline + drillbook + federation stub (v1.6.1)."""
from __future__ import annotations

from organism_desktop.service import DesktopService


def test_hormone_timeline_rows_and_traces():
    svc = DesktopService.create()
    before = len(svc.list_traces(kind="Hormone"))
    out = svc.run_hormone_timeline(windows=8, dt_s=1.0)
    assert out["ok"] is True
    assert out["safe"] is True
    assert len(out["rows"]) == 8
    assert out["rows"][0]["cortisol"] >= 0.0
    assert len(svc.last_hormone_timeline()) == 8
    after = svc.list_traces(kind="Hormone")
    assert len(after) >= before  # may filter by type name


def test_drillbook_requires_confirm():
    svc = DesktopService.create()
    refused = svc.run_degradation_drillbook(confirm=False)
    assert refused["ok"] is False
    assert refused["error"] == "confirm_required"
    assert svc.physiology_snapshot()["degradation_level"] == "L0"


def test_drillbook_l0_to_l4():
    svc = DesktopService.create()
    result = svc.run_degradation_drillbook(confirm=True, target="L4")
    assert result["ok"] is True
    assert result["level"] == "L4"
    assert result["safe"] is True
    assert result["bio_actuation"] is False
    assert len(result["steps"]) >= 2
    assert svc.last_drillbook()["level"] == "L4"
    # Traces should include degradation
    deg = svc.list_traces(kind="Degradation")
    assert deg
    reset = svc.reset_physiology_demo()
    assert reset["level"] == "L0"


def test_federation_stub_not_bft():
    svc = DesktopService.create()
    out = svc.run_federation_stub()
    assert out["ok"] is True
    assert out["stub_only"] is True
    assert out["not_production_bft"] is True
    assert out["quorum"]["agreed"] is True
    assert "node_a" in out["nodes"]
