from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QListWidget, QPushButton, QSplitter

from organism_desktop.panels._widgets import BasePanel, mono_text


class DocsPanel(BasePanel):
    panel_id = "docs"
    panel_title = "Docs / Help"

    def __init__(self, service, parent=None):
        super().__init__(service, parent)
        self.links = self.service.docs_links()
        self.list = QListWidget()
        for link in self.links:
            self.list.addItem(link["title"])
        self.view = mono_text()
        split = QSplitter()
        split.addWidget(self.list)
        split.addWidget(self.view)
        split.setStretchFactor(1, 3)
        self._root.addWidget(split)
        self.list.currentRowChanged.connect(self._load)
        btn = QPushButton("Reload selected")
        btn.clicked.connect(lambda: self._load(self.list.currentRow()))
        self._root.addWidget(btn)
        if self.links:
            self.list.setCurrentRow(0)

    def _load(self, row: int) -> None:
        if row < 0 or row >= len(self.links):
            return
        path = Path(self.links[row]["path"])
        if path.is_file():
            self.view.setPlainText(path.read_text(encoding="utf-8", errors="replace")[:100_000])
        else:
            self.view.setPlainText(f"(missing) {path}")
