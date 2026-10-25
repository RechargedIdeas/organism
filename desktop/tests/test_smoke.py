"""Import / offscreen smoke for Organism Desktop."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from organism_desktop import __version__, panel_ids
from organism_desktop.service import DESKTOP_VERSION, DesktopService


def test_version():
    assert __version__ == "1.8.0"
    assert DESKTOP_VERSION == "1.8.0"


def test_service_home():
    svc = DesktopService.create()
    st = svc.home_status()
    assert st["ok"] is True
    assert st["cpu_everywhere"] is True
    assert st["device"]["runtime"] == "CPU_GENERAL"
    assert st["degradation_level"] == "L0"
    assert st["desktop_version"] == "1.8.0"


def test_offscreen_app_smoke():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from organism_desktop.app import MainWindow

    app = QApplication.instance() or QApplication([])
    svc = DesktopService.create()
    win = MainWindow(svc)
    win.show()
    app.processEvents()
    assert win.nav.count() == len(panel_ids())
    for i in range(win.nav.count()):
        win.nav.setCurrentRow(i)
        app.processEvents()
    win.close()
