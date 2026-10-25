"""Organism Desktop — PySide6 shell."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStatusBar,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from organism_desktop import __version__
from organism_desktop.nav import PANELS
from organism_desktop.panels import PANEL_CLASSES
from organism_desktop.service import DesktopService


class MainWindow(QMainWindow):
    def __init__(self, service: DesktopService):
        super().__init__()
        self.service = service
        self.setWindowTitle(f"Organism Desktop {__version__}")
        self.resize(1280, 800)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)

        left = QVBoxLayout()
        brand = QLabel("Organism")
        f = brand.font()
        f.setPointSize(18)
        f.setBold(True)
        brand.setFont(f)
        left.addWidget(brand)
        sub = QLabel(f"Desktop {__version__} · CPU-first control plane")
        sub.setObjectName("brand_sub")
        sub.setStyleSheet("color: #666;")
        left.addWidget(sub)

        self.cpu_badge = QLabel("CPU Everywhere ●")
        self.cpu_badge.setObjectName("shell_cpu_badge")
        self.cpu_badge.setStyleSheet(
            "background:#0a7; color:white; font-weight:bold; padding:4px 8px; border-radius:4px;"
        )
        left.addWidget(self.cpu_badge)

        self.nav = QListWidget()
        self.nav.setObjectName("nav_list")
        self.nav.setFixedWidth(220)
        for spec in PANELS:
            item = QListWidgetItem(spec.title)
            item.setData(Qt.ItemDataRole.UserRole, spec.id)
            self.nav.addItem(item)
        left.addWidget(self.nav)
        layout.addLayout(left)

        self.stack = QStackedWidget()
        self.stack.setObjectName("panel_stack")
        self._panels: dict[str, QWidget] = {}
        for spec in PANELS:
            cls = PANEL_CLASSES[spec.id]
            panel = cls(service)
            self._panels[spec.id] = panel
            self.stack.addWidget(panel)
        layout.addWidget(self.stack, stretch=1)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready · Ctrl+R refresh panel · Ctrl+Shift+R refresh all · Ctrl+1–0 panels")

        self._install_shortcuts()

    def _install_shortcuts(self) -> None:
        # Refresh current panel
        sc_r = QShortcut(QKeySequence("Ctrl+R"), self)
        sc_r.setObjectName("shortcut_refresh")
        sc_r.activated.connect(self.refresh_current)

        # Refresh all panels + service bundle
        sc_ra = QShortcut(QKeySequence("Ctrl+Shift+R"), self)
        sc_ra.setObjectName("shortcut_refresh_all")
        sc_ra.activated.connect(self.refresh_all)

        # Panel jump Ctrl+1 .. Ctrl+0 (10 panels)
        for i, spec in enumerate(PANELS):
            key = f"Ctrl+{0 if i == 9 else i + 1}"
            sc = QShortcut(QKeySequence(key), self)
            sc.setObjectName(f"shortcut_panel_{spec.id}")
            # Capture index by default-arg
            sc.activated.connect(lambda idx=i: self.nav.setCurrentRow(idx))

        # Also expose as QActions for menu-less discoverability in tests
        act = QAction("Refresh All", self)
        act.setObjectName("action_refresh_all")
        act.setShortcut(QKeySequence("Ctrl+Shift+R"))
        act.triggered.connect(self.refresh_all)
        self.addAction(act)

    def toast(self, message: str, *, error: bool = False, ms: int = 6000) -> None:
        """Non-silent status feedback (errors and info)."""
        if error:
            self._status.setStyleSheet("QStatusBar { color: #a40; font-weight: bold; }")
        else:
            self._status.setStyleSheet("")
        self._status.showMessage(message, ms)

    def refresh_current(self) -> None:
        panel = self.stack.currentWidget()
        try:
            if hasattr(panel, "refresh"):
                panel.refresh()
            self.toast(f"Refreshed {getattr(panel, 'panel_id', 'panel')}")
        except Exception as exc:
            self.toast(f"Refresh failed: {exc}", error=True)

    def refresh_all(self) -> None:
        errors: list[str] = []
        try:
            self.service.refresh_bundle()
        except Exception as exc:
            errors.append(f"bundle:{exc}")
        for pid, panel in self._panels.items():
            try:
                if hasattr(panel, "refresh"):
                    panel.refresh()
            except Exception as exc:
                errors.append(f"{pid}:{exc}")
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        if errors:
            self.toast(f"Refresh-all errors: {'; '.join(errors)}", error=True)
        else:
            self.toast("Refresh-all OK (all panels)")

    def panel_ids(self) -> list[str]:
        return [p.id for p in PANELS]

    def grab_panel_screenshots(self, out_dir: Path) -> list[Path]:
        """Offscreen-friendly: show each panel and save a PNG."""
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        app = QApplication.instance()
        for i, spec in enumerate(PANELS):
            self.nav.setCurrentRow(i)
            if app is not None:
                app.processEvents()
            panel = self._panels[spec.id]
            pix = panel.grab()
            path = out_dir / f"{spec.id}.png"
            pix.save(str(path), "PNG")
            paths.append(path)
        return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="organism-desktop", description="Organism Desktop")
    parser.add_argument("--offscreen", action="store_true", help="Force QT_QPA_PLATFORM=offscreen")
    parser.add_argument("--smoke", action="store_true", help="Build UI and exit (CI)")
    parser.add_argument(
        "--screenshot",
        action="store_true",
        help="Save offscreen panel PNGs under desktop/screenshots/ and exit",
    )
    parser.add_argument(
        "--screenshot-dir",
        type=str,
        default="",
        help="Override screenshot output directory",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.offscreen or args.smoke or args.screenshot:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Organism Desktop")
    app.setFont(QFont("Segoe UI", 11))

    service = DesktopService.create()
    win = MainWindow(service)
    if args.smoke or args.screenshot:
        win.show()
        app.processEvents()
        for i in range(win.nav.count()):
            win.nav.setCurrentRow(i)
            app.processEvents()
        # Smoke also exercises refresh-all once (parity with keyboard path).
        win.refresh_all()
        if args.screenshot:
            root = Path(__file__).resolve().parents[1]
            out = Path(args.screenshot_dir) if args.screenshot_dir else root / "screenshots"
            paths = win.grab_panel_screenshots(out)
            print(f"wrote {len(paths)} screenshots to {out}")
        # Print CLI-parity JSON line for operators / CI grepping.
        parity = service.status_parity()
        print(f"smoke_ok desktop={__version__} cpu_everywhere={parity.get('cpu_everywhere')} "
              f"profile={parity.get('profile')} runtime={parity.get('device_runtime')}")
        return 0

    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
