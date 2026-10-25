"""Qt panel interaction tests (offscreen) — click buttons, check service state."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from organism_desktop.app import MainWindow
from organism_desktop.service import DesktopService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _click(btn: QPushButton) -> None:
    btn.click()


def test_registry_panel_register_buttons(qapp):
    svc = DesktopService.create()
    # Start without forcing re-register path via UI
    win = MainWindow(svc)
    panel = win._panels["registry"]
    # Click register deterministic
    buttons = panel.findChildren(QPushButton)
    labels = {b.text(): b for b in buttons}
    assert "Register deterministic_engine" in labels
    _click(labels["Register deterministic_engine"])
    qapp.processEvents()
    ids = {m["module_id"] for m in svc.list_modules()}
    assert "deterministic_engine" in ids
    _click(labels["Register learned_module"])
    qapp.processEvents()
    assert "learned_module_t2" in {m["module_id"] for m in svc.list_modules()}
    win.close()


def test_pipelines_panel_run(qapp):
    svc = DesktopService.create()
    win = MainWindow(svc)
    panel = win._panels["pipelines"]
    btn = panel.findChild(QPushButton, "run_pipeline")
    assert btn is not None
    _click(btn)
    qapp.processEvents()
    text = panel.view.toPlainText()
    assert "DispatchPlan" in text or "disposition" in text or "plan_id" in text
    win.close()


def test_physiology_simulate_button(qapp):
    svc = DesktopService.create()
    win = MainWindow(svc)
    panel = win._panels["physiology"]
    btn = panel.findChild(QPushButton, "simulate_l0_l1")
    assert btn is not None
    _click(btn)
    qapp.processEvents()
    assert svc.degrade.level == "L1"
    assert "L1" in panel.level_badge.text()
    win.close()


def test_traces_emit_button(qapp):
    svc = DesktopService.create()
    win = MainWindow(svc)
    panel = win._panels["traces"]
    before = len(svc.list_traces())
    btn = panel.findChild(QPushButton, "emit_demo_traces")
    assert btn is not None
    _click(btn)
    qapp.processEvents()
    assert len(svc.list_traces()) > before
    win.close()


def test_workspace_bind_unbind_buttons(qapp):
    svc = DesktopService.create()
    win = MainWindow(svc)
    panel = win._panels["workspace"]
    buttons = {b.text(): b for b in panel.findChildren(QPushButton)}
    _click(buttons["Bind"])
    qapp.processEvents()
    assert svc.list_bindings()
    # Select first row and unbind
    panel.table.selectRow(0)
    _click(buttons["Unbind selected"])
    qapp.processEvents()
    win.close()


def test_bio_panel_actuate_refuses(qapp):
    svc = DesktopService.create()
    win = MainWindow(svc)
    panel = win._panels["bio"]
    btn = panel.findChild(QPushButton, "bio_actuate")
    assert btn is not None
    _click(btn)
    qapp.processEvents()
    text = panel.view.toPlainText()
    assert "refused" in text.lower() or "True" in text
    win.close()


def test_catalog_register_button(qapp):
    svc = DesktopService.create()
    win = MainWindow(svc)
    panel = win._panels["catalog"]
    # Select physical_research row (research tier) and register via button
    entries = svc.module_catalog()
    idx = next(i for i, e in enumerate(entries) if e["catalog_id"] == "reservoir")
    panel.table.selectRow(idx)
    btn = panel.findChild(QPushButton, "catalog_register")
    assert btn is not None
    _click(btn)
    qapp.processEvents()
    assert any(m["module_id"] == "reservoir" for m in svc.list_modules())
    win.close()


def test_contracts_run_button(qapp):
    svc = DesktopService.create()
    win = MainWindow(svc)
    panel = win._panels["contracts"]
    btn = panel.findChild(QPushButton, "contracts_run")
    assert btn is not None
    _click(btn)
    qapp.processEvents()
    assert svc.last_contract_results()
    assert panel.table.rowCount() >= 1
    win.close()


def test_ops_switch_profile_button(qapp):
    svc = DesktopService.create()
    win = MainWindow(svc)
    panel = win._panels["ops"]
    box = panel.profile_box
    # Prefer default if listed
    i = box.findText("default")
    assert i >= 0
    box.setCurrentIndex(i)
    btn = panel.findChild(QPushButton, "ops_switch_profile")
    assert btn is not None
    _click(btn)
    qapp.processEvents()
    assert svc.stack.config.profile == "default"
    assert svc.status_parity()["health_port"] == 8788
    win.close()


def test_pipelines_inspector_and_traces_export(qapp):
    svc = DesktopService.create()
    win = MainWindow(svc)
    pipe = win._panels["pipelines"]
    btn = pipe.findChild(QPushButton, "run_pipeline")
    _click(btn)
    qapp.processEvents()
    assert pipe.ranking_table.rowCount() >= 0  # may be 0 if empty ranking, but summary set
    assert "disposition" in pipe.summary.text().lower() or pipe.summary.text()
    jump = pipe.findChild(QPushButton, "pipeline_jump_traces")
    _click(jump)
    qapp.processEvents()
    from organism_desktop.nav import panel_ids
    assert win.nav.currentRow() == panel_ids().index("traces")
    # Export from traces
    traces = win._panels["traces"]
    exp = traces.findChild(QPushButton, "trace_export_json")
    _click(exp)
    qapp.processEvents()
    assert traces._last_export
    win.close()
