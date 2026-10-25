from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton

from organism_desktop.panels._widgets import BasePanel, mono_text, set_json


class TracesPanel(BasePanel):
    panel_id = "traces"
    panel_title = "Traces / Replay"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.filter = QComboBox()
        self.filter.addItems(["(all)", "Routing", "Degradation", "Hormone", "Workspace", "Lifecycle"])
        self._root.addWidget(self.filter)
        self.view = mono_text()
        self._root.addWidget(self.view)
        row = QHBoxLayout()
        b1 = QPushButton("Refresh")
        b1.clicked.connect(self.refresh)
        b2 = QPushButton("Emit demo traces")
        b2.setObjectName("emit_demo_traces")
        b2.clicked.connect(self._emit)
        b3 = QPushButton("Run sample pipeline")
        b3.clicked.connect(self._sample)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addWidget(b3)
        self._root.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        kind = self.filter.currentText()
        kind_arg = None if kind == "(all)" else kind
        entries = self.service.list_traces(kind=kind_arg)
        set_json(self.view, {"count": len(entries), "filter": kind, "entries": entries})

    def _emit(self) -> None:
        result = self.service.emit_demo_traces()
        set_json(self.view, {"emit": result, "entries": self.service.list_traces()})

    def _sample(self) -> None:
        self.service.run_pipeline()
        self.refresh()
