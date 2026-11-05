"""The work agent's `needs_you` panel (v1.12 W7).

It shows what needs a person, one row each, and the healthy state in one line above them. It reads
the work store beside its writer, so it never blocks the agent.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from organism_sdk.work import operator
from organism_sdk.work.store import WorkStore, default_store_path
from PySide6.QtWidgets import QLabel, QPushButton, QTableWidget

from organism_desktop.panels._widgets import BasePanel, fill_table

HEADERS = ["kind", "item", "detail"]


class NeedsYouPanel(BasePanel):
    panel_id = "needs_you"
    panel_title = "Needs you"

    def __init__(self, service, parent=None, *, store_path: Path | None = None):
        super().__init__(service, parent)
        self._store_path = store_path or default_store_path()
        self.summary = QLabel()
        self.summary.setObjectName("needs_you_summary")
        self.summary.setWordWrap(True)
        self.table = QTableWidget()
        self.table.setObjectName("needs_you_table")
        refresh = QPushButton("Refresh")
        refresh.setObjectName("needs_you_refresh")
        refresh.clicked.connect(self.refresh)
        self._root.addWidget(self.summary)
        self._root.addWidget(self.table)
        self._root.addWidget(refresh)
        self.refresh()

    def refresh(self) -> None:
        if not self._store_path.exists():
            self._show(f"No work store at {self._store_path}. Nothing needs you.", [])
            return
        try:
            with WorkStore(self._store_path, read_only=True) as store:
                report = operator.status(store)
                items = operator.attention(store)
        except sqlite3.Error as error:
            self._show(f"The work store cannot be read: {error}", [])
            return
        state = "paused" if report["paused"] else "running"
        self._show(
            f"{state} · {report['open_tickets']} open · {report['attention']} need you · "
            f"policy {report['policy'] or 'none'}",
            [[item["kind"], item["id"], item["detail"]] for item in items],
        )

    def _show(self, line: str, rows: list[list[str]]) -> None:
        self.summary.setText(line)
        fill_table(self.table, HEADERS, rows)
