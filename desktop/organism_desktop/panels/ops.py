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
        self.cpu_badge.setToolTip("CPU Everywhere: every GPU path has a CPU fallback.")
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
        self.rust_badge = QLabel("rust: ?")
        self.rust_badge.setObjectName("ops_rust_badge")
        self.rust_badge.setToolTip("Read-only Rust workspace inventory (Cargo.toml + crate sources).")
        self.rust_badge.setStyleSheet(
            "background:#444; color:white; font-weight:bold; padding:6px 10px; border-radius:4px;"
        )
        row.addWidget(self.rust_badge)
        row.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(row)
        self._root.addWidget(wrap)

        switch_row = QHBoxLayout()
        switch_row.addWidget(QLabel("Deploy profile:"))
        self.profile_box = QComboBox()
        self.profile_box.setObjectName("ops_profile_box")
        self.profile_box.setToolTip("Switch between cpu_only and default deploy profiles.")
        switch_row.addWidget(self.profile_box)
        apply_btn = QPushButton("Switch profile")
        apply_btn.setObjectName("ops_switch_profile")
        apply_btn.setToolTip("Rebuild MinimalStack with the selected profile (CPU-first).")
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
        btn = QPushButton("Refresh ops")
        btn.setObjectName("ops_refresh")
        btn.setToolTip("Refresh validate-config, wet-lab policy, soak snapshot, rust inventory.")
        btn.clicked.connect(self.refresh)
        btn_row.addWidget(btn)

        soak_btn = QPushButton("Run short soak")
        soak_btn.setObjectName("ops_soak")
        soak_btn.setToolTip("Virtual-clock soak harness → desktop/artifacts/soak_*.json")
        soak_btn.clicked.connect(self._run_soak)
        btn_row.addWidget(soak_btn)

        fuzz_btn = QPushButton("Run short fuzz")
        fuzz_btn.setObjectName("ops_fuzz")
        fuzz_btn.setToolTip("Security fuzz helpers → desktop/artifacts/fuzz_*.json")
        fuzz_btn.clicked.connect(self._run_fuzz)
        btn_row.addWidget(fuzz_btn)

        rust_btn = QPushButton("Probe Rust status")
        rust_btn.setObjectName("ops_rust_probe")
        rust_btn.setToolTip("Read-only cargo metadata + crate inventory (no force-build).")
        rust_btn.clicked.connect(self._probe_rust)
        btn_row.addWidget(rust_btn)

        mp_btn = QPushButton("Multiprocess stub")
        mp_btn.setObjectName("ops_multiprocess")
        mp_btn.setToolTip("Software multi-process oxytocin/BFT sim — not production WAN BFT/TPM.")
        mp_btn.clicked.connect(self._multiprocess)
        btn_row.addWidget(mp_btn)

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
        rust = info.get("rust_runtime") or {}
        present = rust.get("crates_present")
        expected = rust.get("crates_expected")
        self.rust_badge.setText(f"rust: {present}/{expected}" if expected else "rust: ?")
        soak = info.get("soak_snapshot") or {}
        parity = info.get("status_parity") or info.get("cli_parity") or {}
        harness = info.get("last_harness_result") or {}
        harness_hint = ""
        if harness.get("result_path"):
            harness_hint = f" · last_{harness.get('kind')}={harness.get('result_path')}"
        self.summary.setText(
            f"Deploy profile: <b>{profile}</b> · "
            f"health_port={parity.get('health_port')} · "
            f"config ok={info.get('validate', {}).get('ok')} · "
            f"soak reconstructible={soak.get('reconstructible')} · "
            f"soak runbook exists={info.get('soak_runbook_exists')} · "
            f"rust crates={present}/{expected} · "
            f"profiles={[p.get('name') for p in (info.get('profiles') or [])]}"
            f"{harness_hint}"
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
            if hasattr(win, "refresh_all"):
                win.refresh_all()
            else:
                self.refresh()
        except Exception as exc:
            self.view.setPlainText(f"ERROR switching profile:\n{exc}")
            win = self.window()
            if hasattr(win, "toast"):
                win.toast(f"Profile switch failed: {exc}", error=True)

    def _run_soak(self) -> None:
        try:
            result = self.service.run_short_soak_harness(windows=8)
            set_json(self.view, result)
            win = self.window()
            if hasattr(win, "toast"):
                win.toast(f"Soak OK → {result.get('result_path')}")
        except Exception as exc:
            self.view.setPlainText(f"ERROR soak:\n{exc}")
            win = self.window()
            if hasattr(win, "toast"):
                win.toast(f"Soak failed: {exc}", error=True)

    def _run_fuzz(self) -> None:
        try:
            result = self.service.run_short_fuzz_harness(trials=16)
            set_json(self.view, result)
            win = self.window()
            if hasattr(win, "toast"):
                win.toast(f"Fuzz OK → {result.get('result_path')}")
        except Exception as exc:
            self.view.setPlainText(f"ERROR fuzz:\n{exc}")
            win = self.window()
            if hasattr(win, "toast"):
                win.toast(f"Fuzz failed: {exc}", error=True)

    def _probe_rust(self) -> None:
        try:
            result = self.service.rust_runtime_status(probe_cargo=True)
            set_json(self.view, result)
            present = result.get("crates_present")
            expected = result.get("crates_expected")
            self.rust_badge.setText(f"rust: {present}/{expected}")
            win = self.window()
            if hasattr(win, "toast"):
                meta = result.get("cargo_metadata") or {}
                win.toast(
                    f"Rust probe: {present}/{expected} crates · "
                    f"packages={meta.get('package_count', '?')}"
                )
        except Exception as exc:
            self.view.setPlainText(f"ERROR rust probe:\n{exc}")
            win = self.window()
            if hasattr(win, "toast"):
                win.toast(f"Rust probe failed: {exc}", error=True)

    def _multiprocess(self) -> None:
        result = self.service.run_multiprocess_stub(n=3)
        set_json(self.view, result)
        win = self.window()
        if hasattr(win, "toast"):
            win.toast(
                f"Multiprocess stub oxytocin={result.get('oxytocin_accepted')} (not production BFT)",
                error=not result.get("ok"),
            )
