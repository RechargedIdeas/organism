from __future__ import annotations

import json

from PySide6.QtWidgets import QHBoxLayout, QPushButton

from organism_desktop.panels._widgets import BasePanel, mono_text


class WorkspacePanel(BasePanel):
    panel_id = "workspace"
    panel_title = "Workspace"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.view = mono_text()
        self._root.addWidget(self.view)
        row = QHBoxLayout()
        b1 = QPushButton("Refresh bindings")
        b1.clicked.connect(self.refresh)
        b2 = QPushButton("Write demo binding")
        b2.clicked.connect(self._write)
        b3 = QPushButton("Hypervector preview")
        b3.clicked.connect(self._hv)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addWidget(b3)
        self._root.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        bindings = self.service.list_bindings()
        self.view.setPlainText(json.dumps({"bindings": bindings, "count": len(bindings)}, indent=2))

    def _write(self) -> None:
        rec = self.service.write_demo_binding()
        self.view.setPlainText(json.dumps({"wrote": rec, "bindings": self.service.list_bindings()}, indent=2))

    def _hv(self) -> None:
        self.view.setPlainText(json.dumps(self.service.hypervector_preview(seed=42), indent=2))
