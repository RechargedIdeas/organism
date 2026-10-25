from __future__ import annotations

import json

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton

from organism_desktop.panels._widgets import BasePanel, mono_text


class PhysiologyPanel(BasePanel):
    panel_id = "physiology"
    panel_title = "Physiology"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.view = mono_text()
        self._root.addWidget(self.view)
        row = QHBoxLayout()
        self.level = QComboBox()
        self.level.addItems(["L0", "L1", "L2", "L3", "L4"])
        row.addWidget(self.level)
        b1 = QPushButton("Set router level")
        b1.clicked.connect(self._set_level)
        b2 = QPushButton("Refresh")
        b2.clicked.connect(self.refresh)
        row.addWidget(b1)
        row.addWidget(b2)
        self._root.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        self.view.setPlainText(json.dumps(self.service.physiology_snapshot(), indent=2, default=str))

    def _set_level(self) -> None:
        lvl = self.service.set_degradation_level(self.level.currentText())
        self.view.setPlainText(json.dumps({"set_level": lvl, **self.service.physiology_snapshot()}, indent=2, default=str))
