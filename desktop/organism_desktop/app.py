"""Organism Desktop — PySide6 shell."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
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
        sub.setStyleSheet("color: #666;")
        left.addWidget(sub)

        self.nav = QListWidget()
        self.nav.setFixedWidth(220)
        for spec in PANELS:
            item = QListWidgetItem(spec.title)
            item.setData(Qt.ItemDataRole.UserRole, spec.id)
            self.nav.addItem(item)
        left.addWidget(self.nav)
        layout.addLayout(left)

        self.stack = QStackedWidget()
        self._panels: dict[str, QWidget] = {}
        for spec in PANELS:
            cls = PANEL_CLASSES[spec.id]
            panel = cls(service)
            self._panels[spec.id] = panel
            self.stack.addWidget(panel)
        layout.addWidget(self.stack, stretch=1)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

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
        if args.screenshot:
            root = Path(__file__).resolve().parents[1]
            out = Path(args.screenshot_dir) if args.screenshot_dir else root / "screenshots"
            paths = win.grab_panel_screenshots(out)
            print(f"wrote {len(paths)} screenshots to {out}")
        return 0

    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
