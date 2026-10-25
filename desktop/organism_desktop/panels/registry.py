from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QTableWidget

from organism_desktop.panels._widgets import BasePanel, fill_table


class RegistryPanel(BasePanel):
    panel_id = "registry"
    panel_title = "Substrate Registry"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.table = QTableWidget()
        self._root.addWidget(self.table)
        btn = QPushButton("Refresh registry")
        btn.clicked.connect(self.refresh)
        self._root.addWidget(btn)
        self.refresh()

    def refresh(self) -> None:
        mods = self.service.list_modules()
        rows = [
            [m["module_id"], m["version"], m["role"], m["tier"], m["state"], m["may_actuate"], m.get("bio_exploration")]
            for m in mods
        ]
        fill_table(
            self.table,
            ["module_id", "version", "role", "tier", "state", "may_actuate", "bio_exploration"],
            rows,
        )
