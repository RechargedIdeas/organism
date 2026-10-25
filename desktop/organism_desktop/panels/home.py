from __future__ import annotations

import json

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from organism_desktop.panels._widgets import BasePanel, mono_text


class HomePanel(BasePanel):
    panel_id = "home"
    panel_title = "Home / Status"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        row = QHBoxLayout()
        self.cpu_badge = QLabel("CPU Everywhere ●")
        self.cpu_badge.setObjectName("cpu_everywhere_badge")
        self.cpu_badge.setStyleSheet(
            "background:#0a7; color:white; font-weight:bold; padding:6px 10px; border-radius:4px;"
        )
        row.addWidget(self.cpu_badge)
        self.degrade_badge = QLabel("L0")
        self.degrade_badge.setObjectName("degrade_badge")
        self.degrade_badge.setStyleSheet(
            "background:#246; color:white; font-weight:bold; padding:6px 10px; border-radius:4px;"
        )
        row.addWidget(self.degrade_badge)
        row.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(row)
        self._root.addWidget(wrap)

        self.view = mono_text()
        self.view.setObjectName("home_status_view")
        self._root.addWidget(self.view)

        btn_row = QHBoxLayout()
        btn = QPushButton("Refresh status")
        btn.setObjectName("home_refresh")
        btn.clicked.connect(self.refresh)
        btn_row.addWidget(btn)
        soak_btn = QPushButton("Refresh soak snapshot")
        soak_btn.setObjectName("home_soak_refresh")
        soak_btn.clicked.connect(self.refresh)
        btn_row.addWidget(soak_btn)
        btn_row.addStretch(1)
        self._root.addLayout(btn_row)
        self.refresh()

    def refresh(self) -> None:
        try:
            st = self.service.home_status()
        except Exception as exc:  # surface to MainWindow toast if wired
            self.view.setPlainText(f"ERROR refreshing status:\n{exc}")
            win = self.window()
            if hasattr(win, "toast"):
                win.toast(f"Home refresh failed: {exc}", error=True)
            return

        self.degrade_badge.setText(str(st.get("degradation_level", "?")))
        soak = st.get("soak") or {}
        parity = st.get("cli_parity") or {}
        lines = [
            f"Organism SDK:     {st['organism_version']}",
            f"Desktop:          {st['desktop_version']}",
            f"Profile:          {st['profile']}",
            f"Config version:   {st.get('version')}",
            f"CPU Everywhere:   {st['cpu_everywhere']}",
            f"Device runtime:   {st.get('device_runtime') or st['device'].get('runtime')}",
            f"Backend:          {st.get('device_backend') or st['device'].get('backend')}",
            f"prefer_gpu:       {st.get('prefer_gpu')}",
            f"Degradation:      {st['degradation_level']}",
            f"Router level:     {st['router_level']}",
            f"Modules:          {st['module_count']}",
            f"Bindings:         {st['workspace_bindings']}",
            f"Health:           {st['health_host']}:{st['health_port']}",
            f"Serve hint:       {st['serve_hint']}",
            "",
            "=== CLI parity (organism status) ===",
            json.dumps(parity, indent=2, default=str),
            "",
            "=== Soak snapshot (short) ===",
            f"reconstructible: {soak.get('reconstructible')}",
            f"windows/plans:   {soak.get('windows')}/{soak.get('plans')}",
            f"runbook:         {soak.get('runbook_path')} (exists={soak.get('runbook_exists')})",
            f"script:          {soak.get('script_path')} (exists={soak.get('script_exists')})",
            "",
            "Accelerator summary:",
            json.dumps(st.get("accelerator_summary"), indent=2, default=str),
            "",
            "Modules:",
            json.dumps(st.get("modules"), indent=2, default=str),
        ]
        self.view.setPlainText("\n".join(lines))
