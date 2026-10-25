from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from organism_desktop.panels._widgets import BasePanel, fill_table, mono_text, set_json


class PipelinesPanel(BasePanel):
    """Router decide + structured plan / ranking_trace inspector (v1.6)."""

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
        self.task_id = QLineEdit()
        self.task_id.setPlaceholderText("auto if empty")
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
        form.addRow("task_id", self.task_id)
        form.addRow("form", self.form_box)
        form.addRow("safety_tier", self.tier_box)
        form.addRow("deadline_ms", self.deadline)
        form.addRow(self.interp)
        form.addRow(self.determ)
        wrap = QWidget()
        wrap.setLayout(form)
        self._root.addWidget(wrap)

        btn_row = QHBoxLayout()
        btn = QPushButton("Run decide → DispatchPlan")
        btn.setObjectName("run_pipeline")
        btn.clicked.connect(self._run)
        jump = QPushButton("Open result in Traces")
        jump.setObjectName("pipeline_jump_traces")
        jump.clicked.connect(self._jump_traces)
        btn_row.addWidget(btn)
        btn_row.addWidget(jump)
        btn_row.addStretch(1)
        self._root.addLayout(btn_row)

        self.summary = QLabel("No plan yet.")
        self.summary.setObjectName("plan_summary")
        self.summary.setWordWrap(True)
        self._root.addWidget(self.summary)

        split = QSplitter(Qt.Orientation.Vertical)

        ranking_wrap = QWidget()
        rv = QVBoxLayout(ranking_wrap)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(QLabel("Ranking trace (structured)"))
        self.ranking_table = QTableWidget()
        self.ranking_table.setObjectName("ranking_table")
        rv.addWidget(self.ranking_table)

        excl_wrap = QWidget()
        ev = QVBoxLayout(excl_wrap)
        ev.setContentsMargins(0, 0, 0, 0)
        ev.addWidget(QLabel("Excluded modules"))
        self.excluded_table = QTableWidget()
        self.excluded_table.setObjectName("excluded_table")
        ev.addWidget(self.excluded_table)

        split.addWidget(ranking_wrap)
        split.addWidget(excl_wrap)
        self._root.addWidget(split)

        self.view = mono_text()
        self.view.setObjectName("pipeline_raw")
        self.view.setMaximumHeight(160)
        self._root.addWidget(self.view)

    def refresh(self) -> None:
        insp = self.service.inspect_plan()
        if not insp.get("ok"):
            return
        self._render_inspector(insp)

    def _render_inspector(self, insp: dict) -> None:
        s = insp.get("summary") or {}
        self.summary.setText(
            f"<b>{insp.get('disposition')}</b> · plan={s.get('plan_id')} · "
            f"task={s.get('task_id')} · primary=<b>{s.get('primary_module')}</b> "
            f"({s.get('primary_role')} / {s.get('primary_tier')}) · "
            f"fallbacks={s.get('fallbacks')} · excluded={s.get('excluded_count')} · "
            f"cross_check={s.get('cross_check_required')}"
        )
        rank_rows = []
        for step in insp.get("ranking_steps") or []:
            parsed = step.get("parsed") or {}
            rank_rows.append(
                [
                    step.get("step"),
                    parsed.get("kind"),
                    ", ".join(parsed.get("modules") or []),
                    step.get("text"),
                ]
            )
        fill_table(
            self.ranking_table,
            ["step", "kind", "modules", "raw"],
            rank_rows,
        )
        excl_rows = [
            [e.get("module_id"), e.get("reason")] for e in (insp.get("excluded") or [])
        ]
        fill_table(self.excluded_table, ["module_id", "reason"], excl_rows)
        set_json(
            self.view,
            {
                "task": insp.get("task"),
                "disposition": insp.get("disposition"),
                "summary": s,
                "ranking_trace": insp.get("ranking_trace"),
                "plan": insp.get("plan"),
            },
        )

    def _run(self) -> None:
        tid = self.task_id.text().strip() or None
        result = self.service.run_pipeline(
            form=self.form_box.currentText(),
            safety_tier=self.tier_box.currentText(),
            deadline_ms=float(self.deadline.value()),
            task_id=tid,
            requires_interpretability=self.interp.isChecked(),
            requires_determinism=self.determ.isChecked(),
        )
        insp = self.service.inspect_plan()
        self._render_inspector(insp if insp.get("ok") else {
            "ok": True,
            "disposition": result.disposition,
            "task": result.task,
            "summary": {"plan_id": result.plan.get("plan_id"), "task_id": result.task.get("task_id"),
                        "primary_module": (result.plan.get("primary") or {}).get("module_id"),
                        "fallbacks": result.plan.get("fallbacks"), "excluded_count": len(result.plan.get("excluded") or [])},
            "ranking_steps": [{"step": i, "text": t, "parsed": {"kind": "note", "modules": []}}
                              for i, t in enumerate(result.ranking_trace)],
            "ranking_trace": result.ranking_trace,
            "excluded": result.plan.get("excluded") or [],
            "plan": result.plan,
        })

    def _jump_traces(self) -> None:
        """Ask MainWindow to show Traces and apply last-pipeline filter."""
        win = self.window()
        payload = self.service.traces_for_last_pipeline()
        if hasattr(win, "_panels") and "traces" in win._panels:
            # Navigate to traces panel
            from organism_desktop.nav import panel_ids

            ids = panel_ids()
            if "traces" in ids and hasattr(win, "nav"):
                win.nav.setCurrentRow(ids.index("traces"))
            traces = win._panels["traces"]
            if hasattr(traces, "task_filter") and payload.get("task_id"):
                traces.task_filter.setText(str(payload["task_id"]))
            if hasattr(traces, "filter"):
                traces.filter.setCurrentText("Routing")
            if hasattr(traces, "refresh"):
                traces.refresh()
            if hasattr(traces, "detail"):
                set_json(traces.detail, payload)
        set_json(self.view, {"jump": payload})
