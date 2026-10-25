from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem

from organism_desktop.panels._widgets import BasePanel, fill_table, set_json
from PySide6.QtWidgets import QTextEdit


class CatalogPanel(BasePanel):
    """Substrate module catalog with RESEARCH_TIER badges + one-click register."""

    panel_id = "catalog"
    panel_title = "Module Catalog"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.status = QLabel("")
        self.status.setObjectName("catalog_status")
        self.status.setStyleSheet("color:#555;")
        self._root.addWidget(self.status)
        self.table = QTableWidget()
        self.table.setObjectName("catalog_table")
        self._root.addWidget(self.table)
        row = QHBoxLayout()
        b_refresh = QPushButton("Refresh")
        b_refresh.setObjectName("catalog_refresh")
        b_refresh.clicked.connect(self.refresh)
        b_reg = QPushButton("Register selected")
        b_reg.setObjectName("catalog_register")
        b_reg.clicked.connect(self._register_selected)
        row.addWidget(b_refresh)
        row.addWidget(b_reg)
        row.addStretch(1)
        self._root.addLayout(row)
        self.detail = QTextEdit()
        self.detail.setObjectName("catalog_detail")
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(140)
        self._root.addWidget(self.detail)
        self.refresh()

    def refresh(self) -> None:
        entries = self.service.module_catalog()
        rows = [
            [
                e["catalog_id"],
                e["module_id"],
                e["title"],
                e["tier"],
                e.get("research_badge") or ("RESEARCH_TIER" if e.get("research_tier") else ""),
                e["may_actuate_declared"],
                e["registered"],
                e["description"],
            ]
            for e in entries
        ]
        headers = [
            "catalog_id",
            "module_id",
            "title",
            "tier",
            "research",
            "may_actuate",
            "registered",
            "description",
        ]
        fill_table(self.table, headers, rows)
        # Highlight RESEARCH_TIER rows
        research_col = headers.index("research")
        for r, e in enumerate(entries):
            if e.get("research_tier"):
                item = self.table.item(r, research_col)
                if item is not None:
                    item.setForeground(QColor("#a40"))
                    item.setText("RESEARCH_TIER")
        research_n = sum(1 for e in entries if e.get("research_tier"))
        self.status.setText(
            f"{len(entries)} catalog entries · {research_n} RESEARCH_TIER · "
            f"{sum(1 for e in entries if e.get('registered'))} registered"
        )

    def _register_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            self.detail.setPlainText("Select a catalog row first.")
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        catalog_id = item.text()
        try:
            result = self.service.register_catalog_module(catalog_id)
            set_json(self.detail, result)
            win = self.window()
            if hasattr(win, "toast"):
                badge = result.get("research_badge") or ""
                win.toast(f"Registered {result.get('module_id')} {badge}".strip())
        except Exception as e:
            self.detail.setPlainText(f"ERROR: {type(e).__name__}: {e}")
            win = self.window()
            if hasattr(win, "toast"):
                win.toast(f"Catalog register failed: {e}", error=True)
        self.refresh()
