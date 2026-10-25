from __future__ import annotations

import json

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from organism_desktop.panels._widgets import BasePanel, mono_text


class OpsPanel(BasePanel):
    panel_id = "ops"
    panel_title = "Ops / Deploy"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        row = QHBoxLayout()
        self.cpu_badge = QLabel("CPU Everywhere ●")
        self.cpu_badge.setObjectName("ops_cpu_badge")
        self.cpu_badge.setStyleSheet(
            "background:#0a7; color:white; font-weight:bold; padding:6px 10px; border-radius:4px;"
        )
        row.addWidget(self.cpu_badge)
        self.profile_badge = QLabel("profile=?")
        self.profile_badge.setObjectName("ops_profile_badge")
        self.profile_badge.setStyleSheet(
            "background:#246; color:white; font-weight:bold; padding:6px 10px; border-radius:4px;"
        )
        row.addWidget(self.profile_badge)
        row.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(row)
        self._root.addWidget(wrap)

        self.summary = QLabel("")
        self.summary.setObjectName("ops_summary")
        self.summary.setWordWrap(True)
        self._root.addWidget(self.summary)

        self.view = mono_text()
        self.view.setObjectName("ops_view")
        self._root.addWidget(self.view)

        btn_row = QHBoxLayout()
        btn = QPushButton("Refresh ops / validate-config / wet-lab policy")
        btn.setObjectName("ops_refresh")
        btn.clicked.connect(self.refresh)
        btn_row.addWidget(btn)
        soak_btn = QPushButton("Run short soak snapshot")
        soak_btn.setObjectName("ops_soak")
        soak_btn.clicked.connect(self.refresh)
        btn_row.addWidget(soak_btn)
        btn_row.addStretch(1)
        self._root.addLayout(btn_row)
        self.refresh()

    def refresh(self) -> None:
        try:
            info = self.service.ops_info()
        except Exception as exc:
            self.view.setPlainText(f"ERROR refreshing ops:\n{exc}")
            win = self.window()
            if hasattr(win, "toast"):
                win.toast(f"Ops refresh failed: {exc}", error=True)
            return

        profile = info.get("deploy_profile") or "?"
        self.profile_badge.setText(f"deploy: {profile}")
        soak = info.get("soak_snapshot") or {}
        self.summary.setText(
            f"Deploy profile: <b>{profile}</b> · "
            f"config ok={info.get('validate', {}).get('ok')} · "
            f"soak runbook: <code>{info.get('soak_runbook')}</code> "
            f"(exists={info.get('soak_runbook_exists')}) · "
            f"reconstructible={soak.get('reconstructible')}"
        )
        self.view.setPlainText(json.dumps(info, indent=2, default=str))
