"""Navigation registry integrity."""
from __future__ import annotations

from organism_desktop.nav import PANELS, panel_ids
from organism_desktop.panels import PANEL_CLASSES


def test_thirteen_panels():
    ids = panel_ids()
    assert ids == [
        "home",
        "registry",
        "catalog",
        "workspace",
        "pipelines",
        "physiology",
        "metamodel",
        "organism",
        "bio",
        "traces",
        "contracts",
        "ops",
        "docs",
    ]
    assert len(PANELS) == 13
    assert set(PANEL_CLASSES) == set(ids)


def test_panel_specs_have_titles():
    for p in PANELS:
        assert p.title
        assert p.description
