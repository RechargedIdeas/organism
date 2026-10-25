from __future__ import annotations

import json

from PySide6.QtWidgets import QLabel, QPushButton

from organism_desktop.panels._widgets import BasePanel, badge, mono_text


class BioPanel(BasePanel):
    panel_id = "bio"
    panel_title = "Bio-Digital (exploration only)"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        warn = QLabel(
            "HARD SAFETY: control_actuation is refused. may_actuate badges stay False. "
            "Wet-lab SafetyPolicy defaults to deny_all."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #a40; font-weight: bold;")
        self._root.addWidget(warn)
        self._root.addWidget(badge(False))
        self.view = mono_text()
        self._root.addWidget(self.view)
        b1 = QPushButton("Refresh bio status")
        b1.clicked.connect(self.refresh)
        b2 = QPushButton("Attempt actuation (must refuse)")
        b2.clicked.connect(self._actuate)
        self._root.addWidget(b1)
        self._root.addWidget(b2)
        self.refresh()

    def refresh(self) -> None:
        self.view.setPlainText(json.dumps(self.service.bio_status(), indent=2, default=str))

    def _actuate(self) -> None:
        result = self.service.try_bio_actuation(module_id="bio_digital.slime_mold", voltage=0.5)
        self.view.setPlainText(json.dumps({"attempt": result, "status": self.service.bio_status()}, indent=2, default=str))
