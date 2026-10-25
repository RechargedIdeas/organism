"""Small shared Qt helpers."""
from __future__ import annotations

import json
from typing import Any

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget


def mono_text(text: str = "", *, read_only: bool = True) -> QTextEdit:
    w = QTextEdit()
    w.setReadOnly(read_only)
    f = QFont("Menlo")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(11)
    w.setFont(f)
    w.setPlainText(text)
    return w


def title_label(text: str) -> QLabel:
    lab = QLabel(text)
    f = lab.font()
    f.setPointSize(16)
    f.setBold(True)
    lab.setFont(f)
    return lab


def badge(may_actuate: bool) -> QLabel:
    lab = QLabel("may_actuate=True" if may_actuate else "may_actuate=False")
    if may_actuate:
        lab.setStyleSheet("color: #0a7; font-weight: bold; padding: 2px 6px; border: 1px solid #0a7;")
    else:
        lab.setStyleSheet("color: #a40; font-weight: bold; padding: 2px 6px; border: 1px solid #a40;")
    return lab


def set_json(view: QTextEdit, payload: Any) -> None:
    """Render a JSON-serializable payload into a mono text view."""
    view.setPlainText(json.dumps(payload, indent=2, default=str))


def fill_table(table: QTableWidget, headers: list[str], rows: list[list[Any]]) -> None:
    table.clear()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            item = QTableWidgetItem(str(val))
            if headers[c] == "may_actuate" and str(val) == "False":
                item.setForeground(QColor("#a40"))
            if headers[c] == "may_actuate" and str(val) == "True":
                item.setForeground(QColor("#0a7"))
            table.setItem(r, c, item)
    table.resizeColumnsToContents()


class BasePanel(QWidget):
    """Panel base. Subclasses override :meth:`refresh` to reload live data."""

    panel_id: str = ""
    panel_title: str = ""

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self._root = QVBoxLayout(self)
        self._root.addWidget(title_label(self.panel_title))

    def refresh(self) -> None:
        """Reload panel contents from DesktopService.

        Default is a no-op so panels without live state (e.g. Docs) need not
        override. Interactive panels must implement this.
        """
        return
