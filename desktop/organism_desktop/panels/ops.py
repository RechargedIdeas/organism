from __future__ import annotations

import json

from PySide6.QtWidgets import QLabel, QPushButton

from organism_desktop.panels._widgets import BasePanel, mono_text


class OpsPanel(BasePanel):
    panel_id = "ops"
    panel_title = "Ops"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        badge = QLabel("CPU Everywhere ●")
        badge.setStyleSheet(
            "background:#0a7; color:white; font-weight:bold; padding:6px 10px; border-radius:4px;"
        )
        self._root.addWidget(badge)
        self.view = mono_text()
        self._root.addWidget(self.view)
        btn = QPushButton("Refresh ops / validate-config / wet-lab policy")
        btn.clicked.connect(self.refresh)
        self._root.addWidget(btn)
        self.refresh()

    def refresh(self) -> None:
        info = self.service.ops_info()
        self.view.setPlainText(json.dumps(info, indent=2, default=str))
