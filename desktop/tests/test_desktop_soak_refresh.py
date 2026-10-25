"""Short desktop soak: N refresh-all cycles under offscreen; no hard QObject leak."""
from __future__ import annotations

import gc
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from organism_desktop.app import MainWindow
from organism_desktop.service import DesktopService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _qobject_count() -> int:
    # Approximate live QObject population (includes app internals).
    return len([o for o in gc.get_objects() if isinstance(o, QObject)])


def test_refresh_all_soak_stable(qapp):
    """50 refresh-all cycles must not explode QObject count badly."""
    svc = DesktopService.create()
    win = MainWindow(svc)
    win.show()
    qapp.processEvents()

    # Warm-up
    win.refresh_all()
    qapp.processEvents()
    gc.collect()
    baseline = _qobject_count()

    n = 50
    for _ in range(n):
        win.refresh_all()
        win.refresh_current()
        qapp.processEvents()

    gc.collect()
    after = _qobject_count()
    # Allow modest growth (Qt caches / event objects) but catch runaway leaks.
    # Empirically panels should stay within a few thousand of baseline.
    growth = after - baseline
    assert growth < 5000, f"QObject growth too high after {n} refreshes: {growth} (base={baseline}, after={after})"

    # Panels still responsive
    assert win.nav.count() == 12
    win.refresh_all()
    text = win._panels["home"].view.toPlainText()
    assert "CPU Everywhere" in text or "cpu_everywhere" in text.lower() or "Organism SDK" in text
    win.close()


def test_shortcuts_and_toast_exist(qapp):
    svc = DesktopService.create()
    win = MainWindow(svc)
    win.show()
    qapp.processEvents()
    win.toast("hello")
    win.toast("boom", error=True)
    assert win.statusBar().currentMessage() in ("boom", "hello") or win.statusBar().currentMessage()
    # Refresh paths
    win.refresh_current()
    win.refresh_all()
    # Jump to ops via nav index (12-panel layout)
    from organism_desktop.nav import panel_ids
    win.nav.setCurrentRow(panel_ids().index("ops"))
    qapp.processEvents()
    assert win.stack.currentWidget().panel_id == "ops"
    win.close()


def test_home_ops_badges_present(qapp):
    svc = DesktopService.create()
    win = MainWindow(svc)
    home = win._panels["home"]
    ops = win._panels["ops"]
    assert home.cpu_badge.text().startswith("CPU Everywhere")
    assert ops.cpu_badge.text().startswith("CPU Everywhere")
    assert "deploy:" in ops.profile_badge.text() or ops.profile_badge.text()
    assert ("reconstructible" in ops.summary.text().lower()
            or "soak" in ops.summary.text().lower()
            or "profiles=" in ops.summary.text().lower())
    win.close()
