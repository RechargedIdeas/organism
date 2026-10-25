"""Router / plan inspector structured view."""
from __future__ import annotations

from organism_desktop.service import DesktopService, _parse_ranking_line


def test_parse_ranking_order_line():
    parsed = _parse_ranking_line("order=['learned_module_t2', 'deterministic_engine']")
    assert parsed["kind"] == "order"
    assert "learned_module_t2" in parsed["modules"]


def test_inspect_plan_before_decide():
    svc = DesktopService.create()
    insp = svc.inspect_plan()
    assert insp["ok"] is False


def test_inspect_plan_after_decide():
    svc = DesktopService.create()
    result = svc.run_pipeline(task_id="inspect-1", form="pattern_recognition")
    insp = svc.inspect_plan()
    assert insp["ok"] is True
    assert insp["disposition"] == result.disposition
    assert insp["summary"]["task_id"] == "inspect-1"
    assert insp["summary"]["plan_id"] == result.plan["plan_id"]
    assert isinstance(insp["ranking_steps"], list)
    if insp["ranking_steps"]:
        assert "parsed" in insp["ranking_steps"][0]
    assert "excluded" in insp
