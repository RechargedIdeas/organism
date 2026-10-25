from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QWidget,
)

from organism_desktop.panels._widgets import BasePanel, mono_text


class PipelinesPanel(BasePanel):
    panel_id = "pipelines"
    panel_title = "Router / Pipelines"

    FORMS = [
        "pattern_recognition",
        "temporal_prediction",
        "anomaly_detection",
        "constrained_allocation",
        "causal_inference",
        "symbolic_reasoning",
        "signal_analysis",
        "feature_extraction",
        "retrieval",
        "generation",
        "calibration",
        "verification",
        "control_actuation",
    ]

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        form = QFormLayout()
        self.form_box = QComboBox()
        self.form_box.addItems(self.FORMS)
        self.tier_box = QComboBox()
        self.tier_box.addItems(["research", "low", "medium", "high", "critical"])
        self.tier_box.setCurrentText("medium")
        self.deadline = QDoubleSpinBox()
        self.deadline.setRange(1, 1_000_000)
        self.deadline.setValue(1000)
        self.interp = QCheckBox("requires_interpretability")
        self.determ = QCheckBox("requires_determinism")
        form.addRow("form", self.form_box)
        form.addRow("safety_tier", self.tier_box)
        form.addRow("deadline_ms", self.deadline)
        form.addRow(self.interp)
        form.addRow(self.determ)
        wrap = QWidget()
        wrap.setLayout(form)
        self._root.addWidget(wrap)
        btn = QPushButton("Run decide → DispatchPlan")
        btn.clicked.connect(self._run)
        self._root.addWidget(btn)
        self.view = mono_text()
        self._root.addWidget(self.view)

    def _run(self) -> None:
        result = self.service.run_pipeline(
            form=self.form_box.currentText(),
            safety_tier=self.tier_box.currentText(),
            deadline_ms=float(self.deadline.value()),
            requires_interpretability=self.interp.isChecked(),
            requires_determinism=self.determ.isChecked(),
        )
        self.view.setPlainText(
            json.dumps(
                {"task": result.task, "disposition": result.disposition, "plan": result.plan},
                indent=2,
                default=str,
            )
        )
