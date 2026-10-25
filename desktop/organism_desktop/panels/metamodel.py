from __future__ import annotations

import json

from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton

from organism_desktop.panels._widgets import BasePanel, mono_text


class MetamodelPanel(BasePanel):
    panel_id = "metamodel"
    panel_title = "Metamodel (exploration)"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.name = QLineEdit("desktop_organ")
        self._root.addWidget(self.name)
        self.view = mono_text()
        self._root.addWidget(self.view)
        row = QHBoxLayout()
        for label, stage in [
            ("Synthesize", "synthesize"),
            ("Sandbox", "sandbox"),
            ("Shadow", "shadow"),
            ("Promote", "promote"),
            ("Reject", "reject"),
        ]:
            b = QPushButton(label)
            b.clicked.connect(lambda checked=False, s=stage: self._go(s))
            row.addWidget(b)
        self._root.addLayout(row)
        self._organ_id: str | None = None

    def _go(self, stage: str) -> None:
        try:
            if stage == "synthesize":
                data = self.service.metamodel_synthesize(self.name.text().strip() or "desktop_organ")
                self._organ_id = data.get("organ_id")
            else:
                if not self._organ_id:
                    self.view.setPlainText("Synthesize first.")
                    return
                data = self.service.metamodel_advance(
                    self._organ_id, stage, pass_rate=0.95
                )
            self.view.setPlainText(json.dumps(data, indent=2, default=str))
        except Exception as e:
            self.view.setPlainText(f"ERROR: {type(e).__name__}: {e}")
