"""Organism Evolution panel — skills, looks, code promotions, evolution log."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
            "promote gates required · may_actuate=False · CPU Everywhere"
        )
        safety.setObjectName("organism_safety")
        safety.setWordWrap(True)
        safety.setStyleSheet("color:#a40; font-weight:bold;")
        self._root.addWidget(safety)

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
        row.addWidget(b_gen)
        row.addWidget(b_prom)
        skills_l.addLayout(row)
        self.skills_table = QTableWidget()
        self.skills_table.setObjectName("organism_skills_table")
        skills_l.addWidget(self.skills_table)
        tabs.addTab(skills_w, "Evolve Skills")

        # --- Looks ---
        looks_w = QWidget()
        looks_l = QVBoxLayout(looks_w)
        self.looks_brief = QLineEdit("calm teal Organism avatar")
        self.looks_brief.setObjectName("organism_looks_brief")
        self.looks_kind = QComboBox()
        self.looks_kind.setObjectName("organism_looks_kind")
        self.looks_kind.addItems(["avatar", "skin", "icon", "theme"])
        looks_l.addWidget(QLabel("Brief"))
        looks_l.addWidget(self.looks_brief)
        looks_l.addWidget(self.looks_kind)
        b_looks = QPushButton("Evolve looks")
        b_looks.setObjectName("organism_evolve_looks")
        b_looks.clicked.connect(self._evolve_looks)
        looks_l.addWidget(b_looks)
        self.looks_preview = mono_text()
        self.looks_preview.setObjectName("organism_looks_preview")
        looks_l.addWidget(self.looks_preview)
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
        crow.addWidget(b_draft)
        crow.addWidget(b_cprom)
        crow.addWidget(b_cdem)
        code_l.addLayout(crow)
        self.code_table = QTableWidget()
        self.code_table.setObjectName("organism_code_table")
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
        skills = snap.get("skills") or []
        fill_table(
            self.skills_table,
            ["skill_id", "name", "version", "proficiency", "source", "may_control", "research_tier"],
            [
                [
                    s.get("skill_id"),
                    s.get("name"),
                    s.get("version"),
                    s.get("proficiency"),
                    s.get("source"),
                    s.get("may_control"),
                    s.get("research_tier"),
                ]
                for s in skills
            ],
        )
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

    def _evolve_looks(self) -> None:
        result = self.service.evolve_organism_looks(
            self.looks_brief.text().strip() or "Organism avatar",
            kind=self.looks_kind.currentText(),
        )
        set_json(self.looks_preview, result)
        set_json(self.view, result)
        self.refresh()
        self._toast(f"Looks ok={result.get('ok')}", error=not result.get("ok"))

    def _code_draft(self) -> None:
        result = self.service.evolve_organism_code(
            self.code_intent.text().strip() or "Organism code",
            auto_promote=False,
        )
        set_json(self.view, result)
        self.refresh()
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
        self._toast(f"Demoted {bid}")
