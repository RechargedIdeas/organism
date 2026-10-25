from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
)

from organism_desktop.panels._widgets import BasePanel, fill_table, mono_text, set_json


class TracesPanel(BasePanel):
    """Trace explorer — filterable table, JSON export, jump from last pipeline."""

    panel_id = "traces"
    panel_title = "Traces / Replay"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        filt = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.setObjectName("trace_kind_filter")
        self.filter.addItems(
            ["(all)", "Routing", "Degradation", "Hormone", "Workspace", "Lifecycle"]
        )
        self.filter.currentTextChanged.connect(lambda _t: self.refresh())
        self.task_filter = QLineEdit()
        self.task_filter.setObjectName("trace_task_filter")
        self.task_filter.setPlaceholderText("task_id filter (optional)")
        self.task_filter.returnPressed.connect(self.refresh)
        filt.addWidget(QLabel("kind"))
        filt.addWidget(self.filter)
        filt.addWidget(QLabel("task_id"))
        filt.addWidget(self.task_filter)
        self._root.addLayout(filt)

        self.status = QLabel("")
        self.status.setObjectName("trace_status")
        self.status.setStyleSheet("color:#555;")
        self._root.addWidget(self.status)

        self.table = QTableWidget()
        self.table.setObjectName("trace_table")
        self._root.addWidget(self.table)

        self.detail = mono_text()
        self.detail.setObjectName("trace_detail")
        self.detail.setMaximumHeight(140)
        self._root.addWidget(self.detail)

        row = QHBoxLayout()
        b1 = QPushButton("Refresh")
        b1.setObjectName("trace_refresh")
        b1.clicked.connect(self.refresh)
        b2 = QPushButton("Emit demo traces")
        b2.setObjectName("emit_demo_traces")
        b2.clicked.connect(self._emit)
        b3 = QPushButton("Run sample pipeline")
        b3.setObjectName("trace_sample_pipeline")
        b3.clicked.connect(self._sample)
        b4 = QPushButton("Jump from last pipeline")
        b4.setObjectName("trace_jump_pipeline")
        b4.clicked.connect(self._jump_pipeline)
        b5 = QPushButton("Export JSON")
        b5.setObjectName("trace_export_json")
        b5.clicked.connect(self._export)
        for b in (b1, b2, b3, b4, b5):
            row.addWidget(b)
        row.addStretch(1)
        self._root.addLayout(row)
        self._last_export: str | None = None
        self.refresh()

    def _kind_arg(self) -> str | None:
        kind = self.filter.currentText()
        return None if kind == "(all)" else kind

    def _task_arg(self) -> str | None:
        t = self.task_filter.text().strip()
        return t or None

    def refresh(self) -> None:
        entries = self.service.list_traces(
            kind=self._kind_arg(), task_id=self._task_arg(), limit=500
        )
        rows = [
            [
                e.get("seq", ""),
                e.get("kind") or e.get("type", ""),
                e.get("emitted_at", ""),
                e.get("task_id", ""),
                e.get("form")
                or e.get("trigger_kind")
                or e.get("from_level")
                or e.get("source")
                or "",
                e.get("primary_module_id")
                or e.get("to_level")
                or e.get("module_id")
                or e.get("plan_type")
                or "",
            ]
            for e in entries
        ]
        fill_table(
            self.table,
            ["seq", "kind", "emitted_at", "task_id", "detail", "module/level"],
            rows,
        )
        self.status.setText(
            f"{len(entries)} trace(s) · filter={self.filter.currentText()}"
            + (f" · task_id={self._task_arg()}" if self._task_arg() else "")
            + (f" · last_export={self._last_export}" if self._last_export else "")
        )
        set_json(self.detail, {"count": len(entries), "tail": entries[-5:]})

    def _emit(self) -> None:
        result = self.service.emit_demo_traces()
        set_json(self.detail, {"emit": result})
        self.refresh()

    def _sample(self) -> None:
        self.service.run_pipeline()
        self.refresh()

    def _jump_pipeline(self) -> None:
        payload = self.service.traces_for_last_pipeline()
        tid = payload.get("task_id") or ""
        if tid:
            self.task_filter.setText(str(tid))
            self.filter.setCurrentText("Routing")
        set_json(self.detail, payload)
        self.refresh()

    def _export(self) -> None:
        out_dir = Path(tempfile.gettempdir()) / "organism-desktop-traces"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "traces_export.json"
        result = self.service.export_traces_json(
            path, kind=self._kind_arg(), task_id=self._task_arg()
        )
        self._last_export = result.get("path")
        set_json(self.detail, result)
        self.refresh()
