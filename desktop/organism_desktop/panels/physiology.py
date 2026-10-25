from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton

from organism_desktop.panels._widgets import BasePanel, mono_text, set_json


class PhysiologyPanel(BasePanel):
    panel_id = "physiology"
    panel_title = "Physiology"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.level_badge = QLabel("level: L0")
        self.level_badge.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._root.addWidget(self.level_badge)
        self.view = mono_text()
        self._root.addWidget(self.view)
        row = QHBoxLayout()
        self.level = QComboBox()
        self.level.addItems(["L0", "L1", "L2", "L3", "L4"])
        row.addWidget(self.level)
        b1 = QPushButton("Set router level")
        b1.clicked.connect(self._set_level)
        b_demo = QPushButton("Simulate L0→L1 (safe)")
        b_demo.setObjectName("simulate_l0_l1")
        b_demo.clicked.connect(self._demo)
        b_reset = QPushButton("Reset physiology")
        b_reset.clicked.connect(self._reset)
        b2 = QPushButton("Refresh")
        b2.clicked.connect(self.refresh)
        row.addWidget(b1)
        row.addWidget(b_demo)
        row.addWidget(b_reset)
        row.addWidget(b2)
        self._root.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        snap = self.service.physiology_snapshot()
        self.level_badge.setText(
            f"degradation: {snap['degradation_level']} · router: {snap['router_level']}"
        )
        set_json(self.view, snap)

    def _set_level(self) -> None:
        lvl = self.service.set_degradation_level(self.level.currentText())
        set_json(self.view, {"set_router_level": lvl, **self.service.physiology_snapshot()})
        self.level_badge.setText(
            f"degradation: {self.service.degrade.level} · router: {lvl}"
        )

    def _demo(self) -> None:
        result = self.service.simulate_l0_to_l1()
        set_json(self.view, {"demo": result, "snapshot": self.service.physiology_snapshot()})
        self.level_badge.setText(
            f"degradation: {result['level']} · router: {self.service.stack.router.current_level()}"
        )

    def _reset(self) -> None:
        result = self.service.reset_physiology_demo()
        set_json(self.view, {"reset": result, "snapshot": self.service.physiology_snapshot()})
        self.refresh()
