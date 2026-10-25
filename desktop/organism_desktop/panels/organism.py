"""Organism Evolution panel — skills, looks, code, multi-Organism, bundles (v1.8)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from organism_desktop.panels._widgets import BasePanel, fill_table, mono_text, set_json
from PySide6.QtWidgets import QTableWidget


class OrganismPanel(BasePanel):
    panel_id = "organism"
    panel_title = "Organism Evolution"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.header = QLabel("Organism: —")
        self.header.setObjectName("organism_header")
        self.header.setStyleSheet("font-weight:bold; font-size:14px;")
        self.header.setToolTip(
            "Self-evolution for Organisms via promote gates. "
            "Drafts are RESEARCH_TIER until promoted. Bio may_actuate stays False."
        )
        self._root.addWidget(self.header)

        safety = QLabel(
            "Safety: sandbox-only code exec · no arbitrary shell · "
            "promote gates required · may_actuate=False · CPU Everywhere · rollback last promote"
        )
        safety.setObjectName("organism_safety")
        safety.setWordWrap(True)
        safety.setStyleSheet("color:#a40; font-weight:bold;")
        self._root.addWidget(safety)

        # Multi-Organism switcher + export/import (v1.8)
        org_row = QHBoxLayout()
        org_row.addWidget(QLabel("Active Organism"))
        self.organism_combo = QComboBox()
        self.organism_combo.setObjectName("organism_profile_combo")
        self.organism_combo.currentIndexChanged.connect(self._on_organism_combo)
        org_row.addWidget(self.organism_combo, stretch=1)
        self.new_organism_name = QLineEdit("Organism Twin")
        self.new_organism_name.setObjectName("organism_new_name")
        self.new_organism_name.setMaximumWidth(160)
        org_row.addWidget(self.new_organism_name)
        b_create = QPushButton("Create")
        b_create.setObjectName("organism_create")
        b_create.clicked.connect(self._create_organism)
        org_row.addWidget(b_create)
        b_switch = QPushButton("Switch")
        b_switch.setObjectName("organism_switch")
        b_switch.clicked.connect(self._switch_organism)
        org_row.addWidget(b_switch)
        b_export = QPushButton("Export bundle")
        b_export.setObjectName("organism_export_bundle")
        b_export.clicked.connect(self._export_bundle)
        org_row.addWidget(b_export)
        b_import = QPushButton("Re-import last")
        b_import.setObjectName("organism_import_bundle")
        b_import.clicked.connect(self._import_last_bundle)
        org_row.addWidget(b_import)
        self._root.addLayout(org_row)
        self._last_bundle_path: str | None = None
        self._combo_guard = False

        tabs = QTabWidget()
        tabs.setObjectName("organism_tabs")

        # --- Skills ---
        skills_w = QWidget()
        skills_l = QVBoxLayout(skills_w)
        self.skill_name = QLineEdit("navigator")
        self.skill_name.setObjectName("organism_skill_name")
        self.skill_intent = QLineEdit("Navigate feature space for Organism skill pack")
        self.skill_intent.setObjectName("organism_skill_intent")
        skills_l.addWidget(QLabel("Skill name"))
        skills_l.addWidget(self.skill_name)
        skills_l.addWidget(QLabel("Intent"))
        skills_l.addWidget(self.skill_intent)
        row = QHBoxLayout()
        b_gen = QPushButton("Evolve skill")
        b_gen.setObjectName("organism_evolve_skill")
        b_gen.clicked.connect(self._evolve_skill)
        b_prom = QPushButton("Promote selected skill")
        b_prom.setObjectName("organism_promote_skill")
        b_prom.clicked.connect(self._promote_skill)
        b_trace = QPushButton("Improve from trace")
        b_trace.setObjectName("organism_improve_from_trace")
        b_trace.clicked.connect(self._improve_from_trace)
        row.addWidget(b_gen)
        row.addWidget(b_prom)
        row.addWidget(b_trace)
        skills_l.addLayout(row)
        self.skills_table = QTableWidget()
        self.skills_table.setObjectName("organism_skills_table")
        skills_l.addWidget(self.skills_table)
        skills_l.addWidget(QLabel("Skill dependency DAG"))
        self.skill_dag = mono_text()
        self.skill_dag.setObjectName("organism_skill_dag")
        self.skill_dag.setMaximumHeight(140)
        skills_l.addWidget(self.skill_dag)
        tabs.addTab(skills_w, "Evolve Skills")

        # --- Looks ---
        looks_w = QWidget()
        looks_l = QVBoxLayout(looks_w)
        self.looks_brief = QLineEdit("calm teal Organism avatar")
        self.looks_brief.setObjectName("organism_looks_brief")
        self.looks_kind = QComboBox()
        self.looks_kind.setObjectName("organism_looks_kind")
        self.looks_kind.addItems(["avatar", "skin", "icon", "theme", "pack"])
        looks_l.addWidget(QLabel("Brief"))
        looks_l.addWidget(self.looks_brief)
        looks_l.addWidget(self.looks_kind)
        brow = QHBoxLayout()
        b_looks = QPushButton("Evolve looks")
        b_looks.setObjectName("organism_evolve_looks")
        b_looks.clicked.connect(self._evolve_looks)
        b_preview = QPushButton("Refresh asset preview")
        b_preview.setObjectName("organism_asset_preview_btn")
        b_preview.clicked.connect(self._refresh_asset_preview)
        brow.addWidget(b_looks)
        brow.addWidget(b_preview)
        looks_l.addLayout(brow)
        self.looks_preview = mono_text()
        self.looks_preview.setObjectName("organism_looks_preview")
        looks_l.addWidget(self.looks_preview)
        self.asset_preview = mono_text()
        self.asset_preview.setObjectName("organism_asset_preview")
        looks_l.addWidget(QLabel("Asset preview (SVG/JSON text)"))
        looks_l.addWidget(self.asset_preview)
        tabs.addTab(looks_w, "Evolve Looks")

        # --- Code promotions ---
        code_w = QWidget()
        code_l = QVBoxLayout(code_w)
        self.code_intent = QLineEdit("Organism code skill: score(x,y)")
        self.code_intent.setObjectName("organism_code_intent")
        code_l.addWidget(self.code_intent)
        crow = QHBoxLayout()
        b_draft = QPushButton("Draft+pipeline")
        b_draft.setObjectName("organism_code_draft")
        b_draft.clicked.connect(self._code_draft)
        b_cprom = QPushButton("Promote selected bundle")
        b_cprom.setObjectName("organism_code_promote")
        b_cprom.clicked.connect(self._code_promote)
        b_cdem = QPushButton("Demote selected")
        b_cdem.setObjectName("organism_code_demote")
        b_cdem.clicked.connect(self._code_demote)
        b_rb = QPushButton("Rollback last promote")
        b_rb.setObjectName("organism_code_rollback")
        b_rb.clicked.connect(self._code_rollback)
        crow.addWidget(b_draft)
        crow.addWidget(b_cprom)
        crow.addWidget(b_cdem)
        crow.addWidget(b_rb)
        code_l.addLayout(crow)
        code_l.addWidget(QLabel("Pipeline stage progress"))
        self.stage_bar = QProgressBar()
        self.stage_bar.setObjectName("organism_stage_progress")
        self.stage_bar.setRange(0, 6)
        self.stage_bar.setValue(0)
        self.stage_bar.setFormat("%v / %m stages")
        code_l.addWidget(self.stage_bar)
        self.stage_label = QLabel("stage: —")
        self.stage_label.setObjectName("organism_stage_label")
        code_l.addWidget(self.stage_label)
        self.code_table = QTableWidget()
        self.code_table.setObjectName("organism_code_table")
        self.code_table.itemSelectionChanged.connect(self._on_bundle_selected)
        code_l.addWidget(self.code_table)
        tabs.addTab(code_w, "Code Promotions")

        # --- Evolution log ---
        log_w = QWidget()
        log_l = QVBoxLayout(log_w)
        self.log_table = QTableWidget()
        self.log_table.setObjectName("organism_log_table")
        log_l.addWidget(self.log_table)
        b_ref = QPushButton("Refresh")
        b_ref.setObjectName("organism_log_refresh")
        b_ref.clicked.connect(self.refresh)
        log_l.addWidget(b_ref)
        tabs.addTab(log_w, "Evolution Log")

        self._root.addWidget(tabs)
        self.view = mono_text()
        self.view.setObjectName("organism_view")
        self.view.setMaximumHeight(160)
        self._root.addWidget(self.view)
        self.refresh()

    def refresh(self) -> None:
        snap = self.service.organism_snapshot()
        self.header.setText(
            f"Organism: {snap.get('display_name')} ({snap.get('organism_id')}) · "
            f"skills={snap.get('skill_count')} · revs={snap.get('revision_count')} · "
            f"log={snap.get('log_count')}"
        )
        self._fill_organism_combo(snap)
        theme = snap.get("theme") or {}
        if theme.get("palette"):
            win = self.window()
            if hasattr(win, "apply_organism_theme"):
                try:
                    win.apply_organism_theme(theme.get("palette"), qss=theme.get("qss"))
                except Exception:
                    pass
        skills = snap.get("skills") or []
        fill_table(
            self.skills_table,
            [
                "skill_id",
                "name",
                "version",
                "proficiency",
                "shadow",
                "source",
                "depends_on",
                "may_control",
                "research_tier",
            ],
            [
                [
                    s.get("skill_id"),
                    s.get("name"),
                    s.get("version"),
                    s.get("proficiency"),
                    s.get("shadow_score"),
                    s.get("source"),
                    ",".join(s.get("depends_on") or []),
                    s.get("may_control"),
                    s.get("research_tier"),
                ]
                for s in skills
            ],
        )
        dag = self.service.organism_skill_dag()
        set_json(self.skill_dag, dag)
        bundles = self.service.list_code_bundles()
        fill_table(
            self.code_table,
            ["bundle_id", "stage", "shadow_score", "may_control", "backend", "gate_ready"],
            [
                [
                    b.get("bundle_id"),
                    b.get("stage"),
                    b.get("shadow_score"),
                    b.get("may_control"),
                    b.get("backend"),
                    (b.get("gate") or {}).get("ready"),
                ]
                for b in bundles
            ],
        )
        log = snap.get("evolution_log") or []
        fill_table(
            self.log_table,
            ["at", "kind", "summary", "event_id"],
            [[e.get("at"), e.get("kind"), e.get("summary"), e.get("event_id")] for e in log[-50:]],
        )
        set_json(
            self.view,
            {
                "appearance": snap.get("appearance"),
                "last": self.service.last_organism_action(),
            },
        )
        if snap.get("appearance"):
            set_json(self.looks_preview, snap["appearance"])
        if bundles:
            last = bundles[-1]
            self._update_stage_progress(last.get("bundle_id"))

    def _update_stage_progress(self, bundle_id: str | None) -> None:
        if not bundle_id:
            self.stage_bar.setValue(0)
            self.stage_label.setText("stage: —")
            return
        try:
            prog = self.service.code_stage_progress(bundle_id)
        except Exception:
            return
        n = len(prog.get("progress") or [])
        self.stage_bar.setValue(min(6, n))
        self.stage_label.setText(
            f"stage: {prog.get('stage')} · progress={prog.get('progress')} · "
            f"rejected={prog.get('rejected')}"
        )

    def _on_bundle_selected(self) -> None:
        bid = self._selected_bundle_id()
        if bid:
            self._update_stage_progress(bid)

    def _toast(self, msg: str, *, error: bool = False) -> None:
        win = self.window()
        if hasattr(win, "toast"):
            win.toast(msg, error=error)

    def _evolve_skill(self) -> None:
        result = self.service.evolve_organism_skill(
            self.skill_name.text().strip() or "skill",
            intent=self.skill_intent.text().strip() or "Organism skill",
            auto_promote=False,
        )
        set_json(self.view, result)
        self.refresh()
        self._toast(
            f"Skill {result.get('skill', {}).get('name')} stage={result.get('bundle', {}).get('stage')}",
            error=not result.get("ok"),
        )

    def _promote_skill(self) -> None:
        row = self.skills_table.currentRow()
        if row < 0:
            self._toast("Select a skill row", error=True)
            return
        item = self.skills_table.item(row, 0)
        if item is None:
            return
        try:
            result = self.service.promote_organism_skill(item.text())
            set_json(self.view, result)
            self.refresh()
            self._toast(f"Promoted skill {item.text()}")
        except Exception as e:
            self._toast(f"{type(e).__name__}: {e}", error=True)
            set_json(self.view, {"error": str(e)})

    def _improve_from_trace(self) -> None:
        row = self.skills_table.currentRow()
        if row < 0:
            self._toast("Select a skill row", error=True)
            return
        item = self.skills_table.item(row, 0)
        if item is None:
            return
        try:
            result = self.service.improve_organism_skill_from_trace(item.text())
            set_json(self.view, result)
            self.refresh()
            self._toast(f"Improved from trace {item.text()}", error=not result.get("ok"))
        except Exception as e:
            self._toast(f"{type(e).__name__}: {e}", error=True)

    def _evolve_looks(self) -> None:
        kind = self.looks_kind.currentText()
        brief = self.looks_brief.text().strip() or "Organism avatar"
        if kind == "pack":
            result = self.service.evolve_organism_looks_pack(brief)
        else:
            result = self.service.evolve_organism_looks(brief, kind=kind)
        set_json(self.looks_preview, result)
        set_json(self.view, result)
        theme = result.get("theme") or {}
        if theme.get("ok") or theme.get("palette"):
            win = self.window()
            if hasattr(win, "apply_organism_theme"):
                try:
                    win.apply_organism_theme(theme.get("palette"), qss=theme.get("qss"))
                except Exception:
                    pass
        self.refresh()
        self._refresh_asset_preview()
        self._toast(
            f"Looks ok={result.get('ok')} theme={bool(theme)}",
            error=not result.get("ok"),
        )

    def _refresh_asset_preview(self) -> None:
        snap = self.service.organism_snapshot()
        appearance = snap.get("appearance") or {}
        aid = (
            appearance.get("avatar_id")
            or appearance.get("icon_id")
            or appearance.get("theme_id")
            or appearance.get("skin_id")
        )
        if not aid:
            set_json(self.asset_preview, {"preview": None})
            return
        try:
            prev = self.service.organism_asset_preview(aid)
            set_json(self.asset_preview, prev)
        except Exception as e:
            set_json(self.asset_preview, {"error": str(e)})

    def _code_draft(self) -> None:
        result = self.service.evolve_organism_code(
            self.code_intent.text().strip() or "Organism code",
            auto_promote=False,
        )
        set_json(self.view, result)
        self.refresh()
        bid = (result.get("bundle") or {}).get("bundle_id")
        self._update_stage_progress(bid)
        self._toast(
            f"Bundle {result.get('bundle', {}).get('stage')} ready={result.get('gate_ready')}",
            error=not result.get("ok"),
        )

    def _selected_bundle_id(self) -> str | None:
        row = self.code_table.currentRow()
        if row < 0:
            return None
        item = self.code_table.item(row, 0)
        return item.text() if item else None

    def _code_promote(self) -> None:
        bid = self._selected_bundle_id()
        if not bid:
            self._toast("Select a code bundle", error=True)
            return
        try:
            result = self.service.promote_organism_code(bid)
            set_json(self.view, result)
            self.refresh()
            self._update_stage_progress(bid)
            self._toast(f"Promoted {bid}")
        except Exception as e:
            self._toast(f"{type(e).__name__}: {e}", error=True)

    def _code_demote(self) -> None:
        bid = self._selected_bundle_id()
        if not bid:
            self._toast("Select a code bundle", error=True)
            return
        result = self.service.demote_organism_code(bid)
        set_json(self.view, result)
        self.refresh()
        self._update_stage_progress(bid)
        self._toast(f"Demoted {bid}")

    def _code_rollback(self) -> None:
        try:
            result = self.service.rollback_organism_code()
            set_json(self.view, result)
            self.refresh()
            bid = (result.get("bundle") or {}).get("bundle_id")
            self._update_stage_progress(bid)
            self._toast(f"Rolled back {bid}")
        except Exception as e:
            self._toast(f"{type(e).__name__}: {e}", error=True)

    def _fill_organism_combo(self, snap: dict | None = None) -> None:
        snap = snap or self.service.organism_snapshot()
        orgs = snap.get("organisms") or self.service.list_organisms()
        active = snap.get("active_organism_id") or snap.get("organism_id")
        self._combo_guard = True
        self.organism_combo.blockSignals(True)
        self.organism_combo.clear()
        active_idx = 0
        for i, o in enumerate(orgs):
            label = f"{o.get('display_name')} ({o.get('organism_id')})"
            self.organism_combo.addItem(label, o.get("organism_id"))
            if o.get("organism_id") == active or o.get("active"):
                active_idx = i
        if orgs:
            self.organism_combo.setCurrentIndex(active_idx)
        self.organism_combo.blockSignals(False)
        self._combo_guard = False

    def _on_organism_combo(self, _idx: int = 0) -> None:
        # Selection alone does not switch; use Switch button to avoid surprise.
        return

    def _create_organism(self) -> None:
        name = self.new_organism_name.text().strip() or "Organism Twin"
        try:
            result = self.service.create_organism(name, make_active=True)
            set_json(self.view, result)
            self.refresh()
            self._toast(f"Created {result.get('organism', {}).get('display_name')}")
        except Exception as e:
            self._toast(f"{type(e).__name__}: {e}", error=True)

    def _switch_organism(self) -> None:
        oid = self.organism_combo.currentData()
        if not oid:
            self._toast("Select an Organism", error=True)
            return
        try:
            result = self.service.switch_organism(str(oid))
            set_json(self.view, result)
            theme = result.get("theme") or {}
            win = self.window()
            if hasattr(win, "apply_organism_theme") and theme:
                win.apply_organism_theme(theme.get("palette"), qss=theme.get("qss"))
            self.refresh()
            self._toast(f"Switched to {oid}")
        except Exception as e:
            self._toast(f"{type(e).__name__}: {e}", error=True)

    def _export_bundle(self) -> None:
        try:
            result = self.service.export_organism_bundle()
            self._last_bundle_path = result.get("path")
            set_json(self.view, result)
            self.refresh()
            self._toast(f"Exported {result.get('path')}")
        except Exception as e:
            self._toast(f"{type(e).__name__}: {e}", error=True)

    def _import_last_bundle(self) -> None:
        path = self._last_bundle_path
        if not path:
            from pathlib import Path

            root = Path(self.service._repo_root) / "organism_data" / "bundles"
            zips = (
                sorted(root.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
                if root.is_dir()
                else []
            )
            if not zips:
                self._toast("No bundle to import — export first", error=True)
                return
            path = str(zips[0])
        try:
            result = self.service.import_organism_bundle(path, switch_active=True)
            set_json(self.view, result)
            theme = result.get("theme") or {}
            win = self.window()
            if hasattr(win, "apply_organism_theme") and theme:
                win.apply_organism_theme(theme.get("palette"), qss=theme.get("qss"))
            self.refresh()
            self._toast(f"Imported {result.get('organism_id')}", error=not result.get("ok"))
        except Exception as e:
            self._toast(f"{type(e).__name__}: {e}", error=True)
