from __future__ import annotations

import json

from PySide6.QtWidgets import QPushButton

from organism_desktop.panels._widgets import BasePanel, mono_text


class HomePanel(BasePanel):
    panel_id = "home"
    panel_title = "Home / Status"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.view = mono_text()
        self._root.addWidget(self.view)
        btn = QPushButton("Refresh")
        btn.clicked.connect(self.refresh)
        self._root.addWidget(btn)
        self.refresh()

    def refresh(self) -> None:
        st = self.service.home_status()
        lines = [
            f"Organism SDK: {st['organism_version']}",
            f"Desktop:      {st['desktop_version']}",
            f"Profile:      {st['profile']}",
            f"CPU Everywhere: {st['cpu_everywhere']}",
            f"Device runtime: {st['device'].get('runtime')}",
            f"Backend:      {st['device'].get('backend')}",
            f"Degradation:  {st['degradation_level']}",
            f"Router level: {st['router_level']}",
            f"Modules:      {st['module_count']}",
            f"Bindings:     {st['workspace_bindings']}",
            f"Health:       {st['health_host']}:{st['health_port']}",
            f"Serve hint:   {st['serve_hint']}",
            "",
            "Accelerator summary:",
            json.dumps(st.get("accelerator_summary"), indent=2, default=str),
            "",
            "Modules:",
            json.dumps(st.get("modules"), indent=2, default=str),
        ]
        self.view.setPlainText("\n".join(lines))
