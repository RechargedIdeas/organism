"""v1.12 environment panel: add, edit, remove and reveal, with the value masked everywhere else."""

from __future__ import annotations

import logging
import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from organism_desktop.nav import panel_ids
from organism_desktop.panels import PANEL_CLASSES
from organism_desktop.panels.envvars import REVEAL_SECONDS, EnvVarsPanel
from organism_sdk.envstore import MASK, EnvStore, EnvStoreError
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QWidget,
)

SENTINEL = "sentinel-5c2e8d14-not-a-secret"


class MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def names(self) -> list[str]:
        return list(self.values)

    def read(self, name: str) -> str | None:
        return self.values.get(name)

    def write(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> bool:
        return self.values.pop(name, None) is not None


class UnreadableBackend(MemoryBackend):
    def names(self) -> list[str]:
        raise EnvStoreError("the store file cannot be read")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store() -> EnvStore:
    return EnvStore(MemoryBackend())


@pytest.fixture
def panel(app, store: EnvStore):
    widget = EnvVarsPanel(service=None, store=store)
    yield widget
    widget.deleteLater()


def shown_text(panel: EnvVarsPanel) -> str:
    """Every string the panel shows: labels, fields, buttons and table cells."""
    parts: list[str] = []
    for widget in panel.findChildren(QWidget):
        if isinstance(widget, (QLabel, QPushButton)):
            parts.append(widget.text())
        elif isinstance(widget, QLineEdit):
            parts.extend([widget.text(), widget.placeholderText()])
        elif isinstance(widget, QTableWidget):
            for row in range(widget.rowCount()):
                for column in range(widget.columnCount()):
                    item = widget.item(row, column)
                    if item is not None:
                        parts.append(item.text())
    return "\n".join(parts)


def add(panel: EnvVarsPanel, name: str, value: str) -> None:
    panel.name_input.setText(name)
    panel.value_input.setText(value)
    panel.findChild(QPushButton, "envvars_save").click()


def select(panel: EnvVarsPanel, name: str) -> None:
    names = [panel.table.item(row, 0).text() for row in range(panel.table.rowCount())]
    panel.table.selectRow(names.index(name))


def test_the_panel_is_registered_beside_ops(app) -> None:
    assert PANEL_CLASSES["envvars"] is EnvVarsPanel
    ids = panel_ids()
    assert ids[ids.index("ops") + 1] == "envvars"


def test_adding_a_variable_shows_a_mask_not_the_value(panel: EnvVarsPanel, store: EnvStore) -> None:
    add(panel, "ORGANISM_LLM_API_KEY", SENTINEL)
    assert store.get("ORGANISM_LLM_API_KEY").reveal() == SENTINEL
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 0).text() == "ORGANISM_LLM_API_KEY"
    assert panel.table.item(0, 1).text() == MASK
    assert SENTINEL not in shown_text(panel)
    assert panel.value_input.text() == ""
    assert panel.name_input.text() == ""


def test_editing_replaces_the_value_and_keeps_one_row(panel: EnvVarsPanel, store: EnvStore) -> None:
    add(panel, "SOME_TOKEN", SENTINEL)
    select(panel, "SOME_TOKEN")
    assert panel.name_input.text() == "SOME_TOKEN"
    panel.value_input.setText("replacement-value")
    panel.findChild(QPushButton, "envvars_save").click()
    assert store.get("SOME_TOKEN").reveal() == "replacement-value"
    assert panel.table.rowCount() == 1
    assert SENTINEL not in shown_text(panel)


def test_removing_asks_first_and_deletes_on_yes(
    panel: EnvVarsPanel, store: EnvStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    add(panel, "SOME_TOKEN", SENTINEL)
    select(panel, "SOME_TOKEN")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No
    )
    panel.findChild(QPushButton, "envvars_remove").click()
    assert store.names() == ["SOME_TOKEN"]
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    panel.findChild(QPushButton, "envvars_remove").click()
    assert store.names() == []
    assert panel.table.rowCount() == 0


def test_reveal_shows_the_selected_value_until_it_is_hidden_again(
    panel: EnvVarsPanel,
) -> None:
    add(panel, "SOME_TOKEN", SENTINEL)
    select(panel, "SOME_TOKEN")
    reveal = panel.findChild(QPushButton, "envvars_reveal")
    reveal.click()
    assert panel.table.item(0, 1).text() == SENTINEL
    assert panel._reveal_timer.isActive()
    assert panel._reveal_timer.interval() == REVEAL_SECONDS * 1000
    reveal.click()
    assert panel.table.item(0, 1).text() == MASK
    assert not panel._reveal_timer.isActive()


def test_a_reveal_ends_when_its_timer_fires(panel: EnvVarsPanel) -> None:
    add(panel, "SOME_TOKEN", SENTINEL)
    select(panel, "SOME_TOKEN")
    panel.findChild(QPushButton, "envvars_reveal").click()
    assert SENTINEL in shown_text(panel)
    panel._reveal_timer.timeout.emit()
    assert panel.table.item(0, 1).text() == MASK
    assert SENTINEL not in shown_text(panel)


def test_moving_the_selection_masks_a_revealed_value(panel: EnvVarsPanel) -> None:
    add(panel, "AAA_TOKEN", SENTINEL)
    add(panel, "BBB_TOKEN", "other-value")
    select(panel, "AAA_TOKEN")
    panel.findChild(QPushButton, "envvars_reveal").click()
    select(panel, "BBB_TOKEN")
    assert SENTINEL not in shown_text(panel)
    assert panel._revealed is None


def test_a_name_that_is_not_valid_is_refused_without_echo(
    panel: EnvVarsPanel, store: EnvStore
) -> None:
    panel.name_input.setText(f"not valid {SENTINEL}")
    panel.value_input.setText("value")
    panel.findChild(QPushButton, "envvars_save").click()
    assert store.names() == []
    assert panel.status.text().startswith("Not saved")
    assert SENTINEL not in panel.status.text()
    assert SENTINEL not in shown_text(panel).replace(panel.name_input.text(), "")


def test_an_unreadable_store_is_said_plainly(app) -> None:
    panel = EnvVarsPanel(service=None, store=EnvStore(UnreadableBackend()))
    assert "cannot be read" in panel.status.text()
    assert panel.table.rowCount() == 0
    panel.deleteLater()


def test_no_value_reaches_the_log(panel: EnvVarsPanel, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        add(panel, "SOME_TOKEN", SENTINEL)
        select(panel, "SOME_TOKEN")
        reveal = panel.findChild(QPushButton, "envvars_reveal")
        reveal.click()
        reveal.click()
    assert SENTINEL not in caplog.text
