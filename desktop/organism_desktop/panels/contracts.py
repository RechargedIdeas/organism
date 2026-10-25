from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTableWidget

from organism_desktop.panels._widgets import BasePanel, fill_table, mono_text, set_json


class ContractsPanel(BasePanel):
    """Contract / assert panel — last SubstrateContract.validate() results."""

    panel_id = "contracts"
    panel_title = "Contracts / Assert"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.status = QLabel("")
        self.status.setObjectName("contracts_status")
        self.status.setStyleSheet("color:#555;")
        self._root.addWidget(self.status)
        self.table = QTableWidget()
        self.table.setObjectName("contracts_table")
        self._root.addWidget(self.table)
        row = QHBoxLayout()
        b_run = QPushButton("Run contract checks")
        b_run.setObjectName("contracts_run")
        b_run.clicked.connect(self._run)
        b_refresh = QPushButton("Show last results")
        b_refresh.setObjectName("contracts_refresh")
        b_refresh.clicked.connect(self.refresh)
        row.addWidget(b_run)
        row.addWidget(b_refresh)
        row.addStretch(1)
        self._root.addLayout(row)
        self.detail = mono_text()
        self.detail.setObjectName("contracts_detail")
        self._root.addWidget(self.detail)
        # Auto-run once so panel is never empty on first open
        self._run()

    def refresh(self) -> None:
        results = self.service.last_contract_results()
        self._render(results)

    def _run(self) -> None:
        results = self.service.run_contract_checks()
        self._render(results)

    def _render(self, results: list) -> None:
        rows = [
            [
                r.get("module_id"),
                r.get("ok"),
                r.get("issue_count", 0),
                r.get("error_count", r.get("issue_count", 0) if not r.get("ok") else 0),
                r.get("may_actuate"),
                r.get("research_badge")
                or ("RESEARCH_TIER" if r.get("research_tier") else ""),
                r.get("reliability_tier") or r.get("max_safety_tier") or "",
                r.get("error") or "",
            ]
            for r in results
        ]
        fill_table(
            self.table,
            [
                "module_id",
                "ok",
                "issues",
                "errors",
                "may_actuate",
                "research",
                "tier",
                "error",
            ],
            rows,
        )
        ok_n = sum(1 for r in results if r.get("ok"))
        self.status.setText(f"{ok_n}/{len(results)} contracts OK · last check stored")
        set_json(self.detail, {"count": len(results), "results": results})
