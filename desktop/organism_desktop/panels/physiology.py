from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from organism_desktop.panels._widgets import BasePanel, fill_table, mono_text, set_json


class PhysiologyPanel(BasePanel):
    panel_id = "physiology"
    panel_title = "Physiology"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.level_badge = QLabel("level: L0")
        self.level_badge.setObjectName("physio_level_badge")
        self.level_badge.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.level_badge.setToolTip(
            "DegradationMachine level (virtual clock) vs router display level. "
            "Bio actuation is never enabled from this panel."
        )
        self._root.addWidget(self.level_badge)

        safety = QLabel(
            "Safety: virtual-clock demos only · may_actuate stays False · "
            "drillbook requires confirm · no wet-lab GPIO"
        )
        safety.setObjectName("physio_safety")
        safety.setWordWrap(True)
        safety.setStyleSheet("color: #a40; font-weight: bold;")
        safety.setToolTip("See docs/ops/DEGRADATION_DRILLBOOK.md and WETLAB_SAFETY_POLICY.md")
        self._root.addWidget(safety)

        # Hormone timeline table
        self.timeline_empty = QLabel("Hormone timeline: empty — run a virtual-clock demo.")
        self.timeline_empty.setObjectName("hormone_timeline_empty")
        self.timeline_empty.setStyleSheet("color: #666; font-style: italic;")
        self._root.addWidget(self.timeline_empty)
        self.timeline = QTableWidget()
        self.timeline.setObjectName("hormone_timeline_table")
        self.timeline.setToolTip(
            "hormone_state over virtual clock (cortisol / dopamine / oxytocin / melatonin). "
            "HormoneTraceEntry rows also land in Traces."
        )
        self.timeline.setMinimumHeight(140)
        self._root.addWidget(self.timeline)

        # Drillbook / hormone / federation / legacy controls
        row = QHBoxLayout()
        self.level = QComboBox()
        self.level.setObjectName("physio_level_combo")
        self.level.addItems(["L0", "L1", "L2", "L3", "L4"])
        self.level.setToolTip("Router display level only (does not fake physiology hysteresis).")
        row.addWidget(self.level)

        b1 = QPushButton("Set router level")
        b1.setObjectName("physio_set_level")
        b1.setToolTip("Sets router display level without driving DegradationMachine.")
        b1.clicked.connect(self._set_level)

        b_hormone = QPushButton("Hormone timeline")
        b_hormone.setObjectName("physio_hormone_timeline")
        b_hormone.setToolTip("Run virtual-clock hormone_state windows → table + Traces.")
        b_hormone.clicked.connect(self._hormone_timeline)

        b_drill = QPushButton("Drillbook L0→L4…")
        b_drill.setObjectName("physio_drillbook")
        b_drill.setToolTip("Scripted degradation L0→L4 with confirm dialog. Virtual clock only.")
        b_drill.clicked.connect(self._drillbook)

        b_fed = QPushButton("Federation / oxytocin stub")
        b_fed.setObjectName("physio_federation_stub")
        b_fed.setToolTip("Multi-node mirror lag + oxytocin quorum stub (not production BFT).")
        b_fed.clicked.connect(self._federation)

        b_demo = QPushButton("Simulate L0→L1 (safe)")
        b_demo.setObjectName("simulate_l0_l1")
        b_demo.setToolTip("Short L0→L1 FAST hysteresis demo.")
        b_demo.clicked.connect(self._demo)

        b_reset = QPushButton("Reset physiology")
        b_reset.setObjectName("physio_reset")
        b_reset.setToolTip("Reset DegradationMachine to L0 + router L0.")
        b_reset.clicked.connect(self._reset)

        b_traces = QPushButton("Open Traces")
        b_traces.setObjectName("physio_open_traces")
        b_traces.setToolTip("Jump to Traces panel (hormone / degradation entries).")
        b_traces.clicked.connect(self._open_traces)

        b2 = QPushButton("Refresh")
        b2.setObjectName("physio_refresh")
        b2.clicked.connect(self.refresh)

        for b in (b1, b_hormone, b_drill, b_fed, b_demo, b_reset, b_traces, b2):
            row.addWidget(b)
        self._root.addLayout(row)

        self.view = mono_text()
        self.view.setObjectName("physio_view")
        self._root.addWidget(self.view)
        self.refresh()

    def refresh(self) -> None:
        snap = self.service.physiology_snapshot()
        self.level_badge.setText(
            f"degradation: {snap['degradation_level']} · router: {snap['router_level']}"
        )
        rows = self.service.last_hormone_timeline()
        if not rows:
            self.timeline_empty.setText("Hormone timeline: empty — run a virtual-clock demo.")
            self.timeline_empty.show()
            fill_table(
                self.timeline,
                ["t_s", "window_id", "cortisol", "dopamine", "oxytocin", "melatonin", "source"],
                [],
            )
        else:
            self.timeline_empty.setText(f"Hormone timeline: {len(rows)} windows (virtual clock).")
            self.timeline_empty.show()
            fill_table(
                self.timeline,
                ["t_s", "window_id", "cortisol", "dopamine", "oxytocin", "melatonin", "source"],
                [
                    [
                        r.get("t_s"),
                        r.get("window_id"),
                        r.get("cortisol"),
                        r.get("dopamine"),
                        r.get("oxytocin"),
                        r.get("melatonin"),
                        r.get("source"),
                    ]
                    for r in rows
                ],
            )
        hormones = snap.get("hormones") or {}
        if not hormones or hormones.get("error"):
            snap = {
                **snap,
                "hormones_empty_hint": (
                    "No hormone_state yet — click Hormone timeline to generate a demo."
                ),
            }
        set_json(self.view, snap)

    def _set_level(self) -> None:
        lvl = self.service.set_degradation_level(self.level.currentText())
        set_json(self.view, {"set_router_level": lvl, **self.service.physiology_snapshot()})
        self.level_badge.setText(
            f"degradation: {self.service.degrade.level} · router: {lvl}"
        )

    def _hormone_timeline(self) -> None:
        result = self.service.run_hormone_timeline(windows=12, dt_s=1.0)
        set_json(self.view, result)
        self.refresh()
        win = self.window()
        if hasattr(win, "toast"):
            if result.get("ok"):
                win.toast(f"Hormone timeline: {result.get('windows')} windows → Traces")
            else:
                win.toast(result.get("error") or "hormone timeline failed", error=True)

    def _drillbook(self) -> None:
        reply = QMessageBox.question(
            self,
            "Confirm degradation drillbook",
            (
                "Run scripted L0→L4 degradation on the virtual clock?\n\n"
                "• Uses FAST hysteresis only (no wall-clock waits)\n"
                "• Emits DegradationTraceEntry into Traces\n"
                "• Does NOT enable bio / wet-lab actuation\n"
                "• Reset afterward with Reset physiology\n\n"
                "Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            win = self.window()
            if hasattr(win, "toast"):
                win.toast("Drillbook cancelled (confirm required)")
            set_json(
                self.view,
                self.service.run_degradation_drillbook(confirm=False),
            )
            return
        result = self.service.run_degradation_drillbook(confirm=True, target="L4")
        set_json(self.view, result)
        self.refresh()
        win = self.window()
        if hasattr(win, "toast"):
            win.toast(
                f"Drillbook → {result.get('level')} ok={result.get('ok')}",
                error=not result.get("ok"),
            )

    def _federation(self) -> None:
        result = self.service.run_federation_stub()
        set_json(self.view, result)
        win = self.window()
        if hasattr(win, "toast"):
            win.toast(
                f"Federation stub quorum={result.get('quorum', {}).get('agreed')} "
                f"(not production BFT)"
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

    def _open_traces(self) -> None:
        win = self.window()
        if not hasattr(win, "nav"):
            return
        from organism_desktop.nav import panel_ids

        ids = panel_ids()
        if "traces" in ids:
            win.nav.setCurrentRow(ids.index("traces"))
            traces = getattr(win, "_panels", {}).get("traces")
            if traces is not None and hasattr(traces, "refresh"):
                traces.refresh()
