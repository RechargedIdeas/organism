"""The environment panel (v1.12): add, edit, remove and reveal the variables that hold secrets.

Values live in the OS credential store (see organism_sdk.envstore). The table shows each name and a
mask. A value leaves the mask only on an explicit reveal, and hides again after REVEAL_SECONDS. The
panel never copies a value to the clipboard, a log or a status line. A saved value reaches Organism
the next time it starts.
"""

from __future__ import annotations

from organism_sdk.envstore import MASK, EnvStore, EnvStoreError, default_backend
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
)

from organism_desktop.panels._widgets import BasePanel, fill_table

HEADERS = ["name", "value"]
REVEAL_SECONDS = 10


class EnvVarsPanel(BasePanel):
    panel_id = "envvars"
    panel_title = "Environment"

    def __init__(self, service, parent=None, *, store: EnvStore | None = None):
        super().__init__(service, parent)
        self.store = EnvStore(default_backend()) if store is None else store
        self._revealed: str | None = None
        self._reveal_timer = QTimer(self)
        self._reveal_timer.setSingleShot(True)
        self._reveal_timer.setInterval(REVEAL_SECONDS * 1000)
        self._reveal_timer.timeout.connect(self.hide_value)

        self.status = QLabel()
        self.status.setObjectName("envvars_status")
        self.status.setWordWrap(True)
        self.name_input = QLineEdit()
        self.name_input.setObjectName("envvars_name")
        self.name_input.setPlaceholderText("NAME: uppercase letters, digits and underscores")
        self.value_input = QLineEdit()
        self.value_input.setObjectName("envvars_value")
        self.value_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.value_input.setPlaceholderText("value: saved, then cleared")
        self.table = QTableWidget()
        self.table.setObjectName("envvars_table")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._load_selection)

        save = QPushButton("Save")
        save.setObjectName("envvars_save")
        save.clicked.connect(self.save)
        reveal = QPushButton("Reveal / hide")
        reveal.setObjectName("envvars_reveal")
        reveal.clicked.connect(self.reveal)
        remove = QPushButton("Remove")
        remove.setObjectName("envvars_remove")
        remove.clicked.connect(self.remove)

        entry = QHBoxLayout()
        entry.addWidget(self.name_input)
        entry.addWidget(self.value_input)
        entry.addWidget(save)
        actions = QHBoxLayout()
        actions.addWidget(reveal)
        actions.addWidget(remove)
        self._root.addWidget(self.status)
        self._root.addLayout(entry)
        self._root.addWidget(self.table)
        self._root.addLayout(actions)
        self.refresh()

    def refresh(self) -> None:
        selected = self._selected_name()
        try:
            names = self.store.names()
        except EnvStoreError as error:
            self._say(f"The store cannot be read: {error}")
            names = []
        # Selection changes made by the refill are not the user's, so they must not fill the name.
        self.table.blockSignals(True)
        try:
            fill_table(self.table, HEADERS, [[name, self._cell(name)] for name in names])
            if selected in names:
                self.table.selectRow(names.index(selected))
        finally:
            self.table.blockSignals(False)

    def save(self) -> None:
        name = self.name_input.text().strip()
        try:
            self.store.put(name, self.value_input.text())
        except EnvStoreError as error:
            self._say(f"Not saved: {error}.")
            return
        self.value_input.clear()
        self.name_input.clear()
        self.hide_value()
        self._say(f"Saved {name}. It applies the next time Organism starts.")
        self.refresh()

    def remove(self) -> None:
        name = self._selected_name()
        if name is None:
            self._say("Select a variable to remove.")
            return
        answer = QMessageBox.question(self, "Remove variable", f"Remove {name} from the store?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.hide_value()
        try:
            removed = self.store.remove(name)
        except EnvStoreError as error:
            self._say(f"Not removed: {error}.")
            return
        self._say(f"Removed {name}." if removed else f"{name} was not in the store.")
        self.refresh()

    def reveal(self) -> None:
        """Show the selected value for REVEAL_SECONDS, or hide it again if it is already shown."""
        name = self._selected_name()
        if name is None:
            self._say("Select a variable to reveal.")
            return
        if self._revealed == name:
            self.hide_value()
            return
        try:
            if self.store.get(name) is None:
                self._say(f"{name} is not in the store.")
                return
        except EnvStoreError as error:
            self._say(f"The store cannot be read: {error}")
            return
        self._revealed = name
        self._reveal_timer.start()
        self.refresh()
        self._say(f"{name} is shown for {REVEAL_SECONDS} seconds.")

    def hide_value(self) -> None:
        if self._revealed is None:
            return
        self._revealed = None
        self._reveal_timer.stop()
        self.refresh()

    def _cell(self, name: str) -> str:
        if name != self._revealed:
            return MASK
        try:
            secret = self.store.get(name)
        except EnvStoreError:
            return MASK
        return MASK if secret is None else secret.reveal()

    def _selected_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item is not None else None

    def _load_selection(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        if self._revealed is not None and name != self._revealed:
            self.hide_value()
        self.name_input.setText(name)
        self.value_input.clear()

    def _say(self, line: str) -> None:
        self.status.setText(line)
