"""Optional offscreen screenshot smoke — writes under desktop/screenshots/."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from organism_desktop.app import MainWindow
from organism_desktop.nav import PANELS
from organism_desktop.service import DesktopService


def test_offscreen_screenshots(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    svc = DesktopService.create()
    win = MainWindow(svc)
    win.show()
    app.processEvents()
    out = tmp_path / "shots"
    paths = win.grab_panel_screenshots(out)
    assert len(paths) == len(PANELS)
    for p in paths:
        assert p.exists()
        assert p.stat().st_size > 0
    win.close()
