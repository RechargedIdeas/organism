"""Trace explorer: filter, export JSON, jump from pipeline."""
from __future__ import annotations

import json
from pathlib import Path

from organism_desktop.service import DesktopService


def test_list_traces_has_seq_kind_time():
    svc = DesktopService.create()
    svc.emit_demo_traces()
    entries = svc.list_traces(limit=50)
    assert entries
    e = entries[-1]
    assert "seq" in e
    assert "kind" in e
    assert e["type"].endswith("TraceEntry") or "Trace" in e["type"]


def test_filter_by_kind_and_task_id():
    svc = DesktopService.create()
    svc.run_pipeline(task_id="trace-filter-1")
    svc.emit_demo_traces()
    routing = svc.list_traces(kind="Routing")
    assert routing
    assert all("Routing" in e["type"] or e.get("kind") == "Routing" for e in routing)
    by_task = svc.list_traces(task_id="trace-filter-1")
    assert by_task
    assert all(e.get("task_id") == "trace-filter-1" for e in by_task)


def test_export_traces_json(tmp_path: Path):
    svc = DesktopService.create()
    svc.emit_demo_traces()
    out = tmp_path / "traces.json"
    result = svc.export_traces_json(out, kind="Routing")
    assert result["ok"] is True
    assert result["count"] >= 1
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["count"] == result["count"]
    assert data["entries"]


def test_jump_from_last_pipeline():
    svc = DesktopService.create()
    svc.run_pipeline(task_id="jump-me")
    payload = svc.traces_for_last_pipeline()
    assert payload["ok"] is True
    assert payload["task_id"] == "jump-me"
    assert payload["count"] >= 1
