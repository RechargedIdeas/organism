"""v1.12 W7, the `needs_you` panel: it lists what needs a person, and states the rest in one line."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from organism_desktop.nav import panel_ids
from organism_desktop.panels import PANEL_CLASSES
from organism_desktop.panels.needs_you import NeedsYouPanel
from organism_sdk.work.domain import (
    Assignment,
    AssignmentState,
    Mandate,
    Report,
    Strength,
    Ticket,
    Via,
)
from organism_sdk.work.store import WorkStore


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def ticket(store: WorkStore, ticket_id: str, report: Report | None = None) -> None:
    mandate = Mandate(
        policy_version="sha256:test",
        strength=Strength.EXPLICIT,
        via=Via.ADDRESSED,
        source="github",
        row="repo",
        sender="alice",
        rules=("ci-fix",),
    )
    assignment = Assignment(id=f"a-{ticket_id}", ticket_id=ticket_id, state=AssignmentState.RUNNING)
    store.save_ticket(
        Ticket(id=ticket_id, mandate=mandate, assignment=assignment, latest_report=report)
    )


def test_the_panel_sits_beside_home_and_is_registered(app) -> None:
    assert panel_ids()[1] == "needs_you"
    assert PANEL_CLASSES["needs_you"] is NeedsYouPanel


def test_it_lists_only_what_needs_a_person(app, tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    with WorkStore(path) as store:
        ticket(store, "t-working")
        ticket(store, "t-blocked", Report.BLOCKED)
    panel = NeedsYouPanel(None, store_path=path)
    assert panel.summary.text() == "running · 2 open · 1 need you · policy none"
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 1).text() == "t-blocked"


def test_it_reads_beside_a_writer_that_holds_the_store(app, tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    with WorkStore(path) as store:
        ticket(store, "t-blocked", Report.BLOCKED)
        panel = NeedsYouPanel(None, store_path=path)
        assert panel.table.rowCount() == 1


def test_refresh_shows_what_changed_since(app, tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    with WorkStore(path) as store:
        panel = NeedsYouPanel(None, store_path=path)
        assert panel.table.rowCount() == 0
        ticket(store, "t-blocked", Report.BLOCKED)
        panel.refresh()
        assert panel.table.rowCount() == 1


def test_without_a_store_it_says_nothing_needs_the_person(app, tmp_path: Path) -> None:
    panel = NeedsYouPanel(None, store_path=tmp_path / "missing.sqlite")
    assert "Nothing needs you" in panel.summary.text()
    assert panel.table.rowCount() == 0
