from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTextEdit

from organism_desktop.panels._widgets import BasePanel, fill_table, set_json


class WorkspacePanel(BasePanel):
    panel_id = "workspace"
    panel_title = "Workspace"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.status = QLabel("")
        self._root.addWidget(self.status)
        self.table = QTableWidget()
        self._root.addWidget(self.table)
        tag_row = QHBoxLayout()
        self.tag = QLineEdit("desktop.demo")
        tag_row.addWidget(QLabel("tag"))
        tag_row.addWidget(self.tag)
        self._root.addLayout(tag_row)
        row = QHBoxLayout()
        b1 = QPushButton("Refresh")
        b1.clicked.connect(self.refresh)
        b2 = QPushButton("Bind")
        b2.clicked.connect(self._write)
        b3 = QPushButton("Unbind selected")
        b3.clicked.connect(self._unbind)
        b4 = QPushButton("Hypervector preview")
        b4.clicked.connect(self._hv)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addWidget(b3)
        row.addWidget(b4)
        self._root.addLayout(row)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(140)
        self._root.addWidget(self.detail)
        self.refresh()

    def refresh(self) -> None:
        bindings = self.service.list_bindings()
        rows = [
            [b["binding_id"], ",".join(b.get("tags") or []), b.get("module_id", ""), b.get("role_prefix", "")]
            for b in bindings
        ]
        fill_table(self.table, ["binding_id", "tags", "module_id", "role_prefix"], rows)
        self.status.setText(f"{len(bindings)} binding(s)")

    def _write(self) -> None:
        rec = self.service.write_demo_binding(tag=self.tag.text().strip() or "desktop.demo")
        set_json(self.detail, {"wrote": rec})
        self.refresh()

    def _unbind(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            self.detail.setPlainText("Select a binding row first.")
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        result = self.service.unbind_binding(item.text())
        set_json(self.detail, result)
        self.refresh()

    def _hv(self) -> None:
        prev = self.service.hypervector_preview(seed=42)
        spark = prev.get("sparkline") or ""
        self.status.setText(f"{self.status.text().split('·')[0].strip()} · HV spark: {spark[:24]}")
        set_json(self.detail, prev)
