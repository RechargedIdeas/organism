"""Pipeline decide round-trip via DesktopService."""
from __future__ import annotations

from organism_desktop.service import DesktopService


def test_pipeline_decide_round_trip():
    svc = DesktopService.create()
    result = svc.run_pipeline(
        form="pattern_recognition",
        safety_tier="medium",
        task_id="desktop-test-1",
        requires_determinism=False,
    )
    assert result.disposition in {"DISPATCH", "HOLD", "DEGRADED"}
    assert result.task["task_id"] == "desktop-test-1"
    assert result.plan["task_id"] == result.task["task_id"]
    assert result.plan["plan_id"]
    assert "ranking_trace" in result.plan
    if result.disposition == "DISPATCH":
        assert result.plan["primary"] is not None
        assert result.plan["primary"]["module_id"]


def test_control_actuation_routes_to_governance():
    svc = DesktopService.create()
    result = svc.run_pipeline(form="control_actuation", safety_tier="critical")
    assert result.plan["disposition"]
    primary = (result.plan.get("primary") or {}).get("module_id")
    assert primary not in {"bio_digital.slime_mold", "bio_digital.mycelium"}


def test_pipeline_emits_routing_trace():
    svc = DesktopService.create()
    before = len(svc.list_traces(kind="Routing"))
    svc.run_pipeline(form="pattern_recognition")
    after = svc.list_traces(kind="Routing")
    assert len(after) > before
