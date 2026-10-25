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
            "Wet-lab SafetyPolicy defaults to deny_all. Desktop never enables GPIO / wet hardware."
        )
        warn.setObjectName("bio_safety_banner")
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #a40; font-weight: bold;")
        warn.setToolTip(
            "ActuationRefused on every control path. Twin / HAL are stub backends only."
        )
        self._root.addWidget(warn)
        self._root.addWidget(badge(False))
        self.empty = QLabel("")
        self.empty.setObjectName("bio_empty_hint")
        self.empty.setStyleSheet("color: #666; font-style: italic;")
        self.empty.setWordWrap(True)
        self._root.addWidget(self.empty)
        self.view = mono_text()
        self.view.setObjectName("bio_view")
        self._root.addWidget(self.view)
        b1 = QPushButton("Refresh bio / twin status")
        b1.setObjectName("bio_refresh")
        b1.setToolTip("Refresh HAL twin + registered bio modules (exploration only).")
        b1.clicked.connect(self.refresh)
        b2 = QPushButton("Attempt actuation (must refuse)")
        b2.setObjectName("bio_actuate")
        b2.setToolTip("Intentionally attempts actuation — Desktop must raise ActuationRefused.")
        b2.clicked.connect(self._actuate)
        b3 = QPushButton("HAL twin sample only")
        b3.setObjectName("bio_twin")
        b3.setToolTip("Read stub HAL twin telemetry. Never actuates.")
        b3.clicked.connect(self._twin)
        self._root.addWidget(b1)
        self._root.addWidget(b2)
        self._root.addWidget(b3)
        self.refresh()

    def refresh(self) -> None:
        status = self.service.bio_status()
        mods = status.get("modules") or status.get("bio_modules") or []
        if not mods and not status.get("hal"):
            self.empty.setText(
                "Empty / stub: bio modules may be unregistered; HAL twin uses PHYSARUM_LIMITS stub. "
                "Actuation remains hard-refused regardless."
            )
        else:
            self.empty.setText(
                "Exploration view only — may_actuate=False · actuation buttons must refuse."
            )
        set_json(self.view, status)

    def _actuate(self) -> None:
        result = self.service.try_bio_actuation(module_id="bio_digital.slime_mold", voltage=0.5)
        set_json(self.view, {"attempt": result, "status": self.service.bio_status()})
        win = self.window()
        if hasattr(win, "toast"):
            refused = result.get("refused") or result.get("ok") is False
            win.toast(
                "Actuation refused (expected)" if refused else "Unexpected actuation result",
                error=not refused,
            )

    def _twin(self) -> None:
        set_json(self.view, {"twin": self.service.refresh_bio_twin()})
