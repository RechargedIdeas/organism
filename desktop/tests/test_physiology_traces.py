"""Physiology L0→L1 demo + trace emit/list."""
from __future__ import annotations

from organism_desktop.service import DesktopService


def test_simulate_l0_to_l1():
    svc = DesktopService.create()
    assert svc.physiology_snapshot()["degradation_level"] == "L0"
    result = svc.simulate_l0_to_l1()
    assert result["ok"] is True
    assert result["level"] == "L1"
    assert result["safe"] is True
    snap = svc.physiology_snapshot()
    assert snap["degradation_level"] == "L1"
    assert snap["transitions"]
    reset = svc.reset_physiology_demo()
    assert reset["level"] == "L0"


def test_emit_and_list_traces():
    svc = DesktopService.create()
    before = len(svc.list_traces())
    out = svc.emit_demo_traces()
    assert out["emitted"] >= 1
    entries = svc.list_traces()
    assert len(entries) > before
    types = {e["type"] for e in entries}
    assert "RoutingTraceEntry" in types
    assert "DegradationTraceEntry" in types
    # Hormone may be present when v02 sink attached
    routing = svc.list_traces(kind="Routing")
    assert routing
    assert all("Routing" in e["type"] for e in routing)
