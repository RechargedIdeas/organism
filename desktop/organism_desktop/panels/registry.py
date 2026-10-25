from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTableWidget

from organism_desktop.panels._widgets import BasePanel, fill_table, set_json
from PySide6.QtWidgets import QTextEdit


class RegistryPanel(BasePanel):
    panel_id = "registry"
    panel_title = "Substrate Registry"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.status = QLabel("")
        self.status.setStyleSheet("color: #555;")
        self._root.addWidget(self.status)
        self.table = QTableWidget()
        self._root.addWidget(self.table)
        row = QHBoxLayout()
        b_refresh = QPushButton("Refresh")
        b_refresh.clicked.connect(self.refresh)
        b_det = QPushButton("Register deterministic_engine")
        b_det.clicked.connect(lambda: self._register("deterministic"))
        b_learn = QPushButton("Register learned_module")
        b_learn.clicked.connect(lambda: self._register("learned"))
        b_dereg = QPushButton("Deregister selected")
        b_dereg.clicked.connect(self._deregister_selected)
        row.addWidget(b_refresh)
        row.addWidget(b_det)
        row.addWidget(b_learn)
        row.addWidget(b_dereg)
        self._root.addLayout(row)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(120)
        self._root.addWidget(self.detail)
        self.refresh()

    def refresh(self) -> None:
        mods = self.service.list_modules()
        rows = [
            [
                m["module_id"],
                m["version"],
                m["role"],
                m["tier"],
                m["state"],
                m["may_actuate"],
                m.get("bio_exploration"),
            ]
            for m in mods
        ]
        fill_table(
            self.table,
            ["module_id", "version", "role", "tier", "state", "may_actuate", "bio_exploration"],
            rows,
        )
        self.status.setText(f"{len(mods)} module(s) registered")

    def _register(self, kind: str) -> None:
        try:
            result = self.service.register_core_module(kind)  # type: ignore[arg-type]
            set_json(self.detail, result)
        except Exception as e:
            self.detail.setPlainText(f"ERROR: {type(e).__name__}: {e}")
        self.refresh()

    def _deregister_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            self.detail.setPlainText("Select a module row first.")
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        mid = item.text()
        try:
            result = self.service.deregister_module(mid)
            set_json(self.detail, result)
        except Exception as e:
            self.detail.setPlainText(f"ERROR: {type(e).__name__}: {e}")
        self.refresh()
