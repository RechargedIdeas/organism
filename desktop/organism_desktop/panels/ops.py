from __future__ import annotations

import json

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from organism_desktop.panels._widgets import BasePanel, mono_text, set_json


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

        # Multi-profile switcher (v1.6)
        switch_row = QHBoxLayout()
        switch_row.addWidget(QLabel("Deploy profile:"))
        self.profile_box = QComboBox()
        self.profile_box.setObjectName("ops_profile_box")
        switch_row.addWidget(self.profile_box)
        apply_btn = QPushButton("Switch profile")
        apply_btn.setObjectName("ops_switch_profile")
        apply_btn.clicked.connect(self._switch_profile)
        switch_row.addWidget(apply_btn)
        switch_row.addStretch(1)
        self._root.addLayout(switch_row)

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

    def _reload_profile_box(self, profiles: list, active: str) -> None:
        names = [p["name"] for p in profiles if p.get("ok")]
        cur = self.profile_box.currentText()
        self.profile_box.blockSignals(True)
        self.profile_box.clear()
        self.profile_box.addItems(names)
        target = active if active in names else (cur if cur in names else (names[0] if names else ""))
        if target:
            self.profile_box.setCurrentText(target)
        self.profile_box.blockSignals(False)

    def refresh(self) -> None:
        try:
            info = self.service.ops_info()
        except Exception as exc:
            self.view.setPlainText(f"ERROR refreshing ops:\n{exc}")
            win = self.window()
            if hasattr(win, "toast"):
                win.toast(f"Ops refresh failed: {exc}", error=True)
            return

        profile = info.get("deploy_profile") or info.get("active_profile") or "?"
        self.profile_badge.setText(f"deploy: {profile}")
        self._reload_profile_box(info.get("profiles") or [], str(profile))
        soak = info.get("soak_snapshot") or {}
        parity = info.get("status_parity") or info.get("cli_parity") or {}
        self.summary.setText(
            f"Deploy profile: <b>{profile}</b> · "
            f"health_port={parity.get('health_port')} · "
            f"config ok={info.get('validate', {}).get('ok')} · "
            f"soak reconstructible={soak.get('reconstructible')} · "
            f"soak runbook exists={info.get('soak_runbook_exists')} · "
            f"profiles={[p.get('name') for p in (info.get('profiles') or [])]}"
        )
        self.view.setPlainText(json.dumps(info, indent=2, default=str))

    def _switch_profile(self) -> None:
        name = self.profile_box.currentText().strip()
        if not name:
            return
        try:
            result = self.service.switch_deploy_profile(name)
            set_json(self.view, result)
            win = self.window()
            if hasattr(win, "toast"):
                delta = result.get("delta") or {}
                win.toast(
                    f"Switched to {result.get('profile')} · delta_keys={list(delta)}"
                )
            # Refresh related panels that cache stack state
            if hasattr(win, "refresh_all"):
                win.refresh_all()
            else:
                self.refresh()
        except Exception as exc:
            self.view.setPlainText(f"ERROR switching profile:\n{exc}")
            win = self.window()
            if hasattr(win, "toast"):
                win.toast(f"Profile switch failed: {exc}", error=True)
