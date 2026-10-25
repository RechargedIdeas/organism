"""Qt interactions for physiology timeline / drillbook / ops harness (offscreen)."""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from organism_desktop.app import MainWindow
from organism_desktop.service import DesktopService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_physiology_hormone_button(qapp, monkeypatch):
    svc = DesktopService.create()
    win = MainWindow(svc)
    win.show()
    qapp.processEvents()
    panel = win._panels["physiology"]
    # Auto-accept would be needed for drillbook; hormone has no dialog
    panel._hormone_timeline()
    qapp.processEvents()
    assert len(svc.last_hormone_timeline()) >= 1
    assert panel.timeline.rowCount() >= 1


def test_physiology_drillbook_cancel(qapp, monkeypatch):
    svc = DesktopService.create()
    win = MainWindow(svc)
    panel = win._panels["physiology"]

    def _no(*_a, **_k):
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", _no)
    panel._drillbook()
    assert svc.physiology_snapshot()["degradation_level"] == "L0"


def test_physiology_drillbook_confirm(qapp, monkeypatch):
    svc = DesktopService.create()
    win = MainWindow(svc)
    panel = win._panels["physiology"]

    def _yes(*_a, **_k):
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", _yes)
    panel._drillbook()
    assert svc.degrade.level == "L4"


def test_ops_soak_fuzz_buttons(qapp):
    svc = DesktopService.create()
    win = MainWindow(svc)
    panel = win._panels["ops"]
    panel._run_soak()
    assert svc.last_harness_result()["kind"] == "soak"
    panel._run_fuzz()
    assert svc.last_harness_result()["kind"] == "fuzz"
    panel._probe_rust()
    assert svc.last_rust_status() is not None
