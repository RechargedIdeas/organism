from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton

from organism_desktop.panels._widgets import BasePanel, badge, mono_text, set_json


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
        b1 = QPushButton("Refresh bio / twin status")
        b1.setObjectName("bio_refresh")
        b1.clicked.connect(self.refresh)
        b2 = QPushButton("Attempt actuation (must refuse)")
        b2.setObjectName("bio_actuate")
        b2.clicked.connect(self._actuate)
        b3 = QPushButton("HAL twin sample only")
        b3.clicked.connect(self._twin)
        self._root.addWidget(b1)
        self._root.addWidget(b2)
        self._root.addWidget(b3)
        self.refresh()

    def refresh(self) -> None:
        set_json(self.view, self.service.bio_status())

    def _actuate(self) -> None:
        result = self.service.try_bio_actuation(module_id="bio_digital.slime_mold", voltage=0.5)
        set_json(self.view, {"attempt": result, "status": self.service.bio_status()})

    def _twin(self) -> None:
        set_json(self.view, {"twin": self.service.refresh_bio_twin()})
