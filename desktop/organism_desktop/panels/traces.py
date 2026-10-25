from __future__ import annotations

import json

from PySide6.QtWidgets import QPushButton

from organism_desktop.panels._widgets import BasePanel, mono_text


class TracesPanel(BasePanel):
    panel_id = "traces"
    panel_title = "Traces / Replay"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.view = mono_text()
        self._root.addWidget(self.view)
        b1 = QPushButton("Refresh traces")
        b1.clicked.connect(self.refresh)
        b2 = QPushButton("Run sample pipeline (for traces)")
        b2.clicked.connect(self._sample)
        self._root.addWidget(b1)
        self._root.addWidget(b2)
        self.refresh()

    def refresh(self) -> None:
        entries = self.service.list_traces()
        self.view.setPlainText(json.dumps({"count": len(entries), "entries": entries}, indent=2))

    def _sample(self) -> None:
        self.service.run_pipeline()
        self.refresh()
