"""v1.7 Organism Evolution Desktop surfaces."""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from organism_desktop.app import MainWindow
from organism_desktop.nav import panel_ids
from organism_desktop.service import ActuationRefused, DESKTOP_VERSION, DesktopService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_nav_includes_organism():
    ids = panel_ids()
    assert "organism" in ids
    assert ids.index("organism") == ids.index("metamodel") + 1


def test_service_evolution_roundtrip():
    assert DESKTOP_VERSION == "1.7.0"
    svc = DesktopService.create()
    snap = svc.organism_snapshot()
    assert snap["organism_id"]
    assert snap["may_actuate"] is False
    skill = svc.evolve_organism_skill("analyst", intent="analyze signals", auto_promote=False)
    assert skill["ok"]
    assert skill["bundle"]["stage"] == "SHADOW_SCORED"
    promoted = svc.promote_organism_skill(skill["skill"]["skill_id"])
    assert promoted["skill"]["may_control"] is True
    looks = svc.evolve_organism_looks("amber Organism icon", kind="icon")
    assert looks["ok"]
    code = svc.evolve_organism_code("Organism scorer", auto_promote=True)
    assert code["bundle"]["may_control"] is True
    dem = svc.demote_organism_code(code["bundle"]["bundle_id"])
    assert dem["bundle"]["may_control"] is False
    # unsafe promote refused
    raw = svc.code_pipeline.start("early")
    with pytest.raises(ActuationRefused):
        svc.promote_organism_code(raw.bundle_id)
    # no sophont naming
    assert "sophont" not in snap["organism_id"].lower()


def test_organism_panel_qt(qapp):
    svc = DesktopService.create()
    win = MainWindow(svc)
    win.show()
    qapp.processEvents()
    assert "organism" in win._panels
    panel = win._panels["organism"]
    panel._evolve_skill()
    qapp.processEvents()
    assert svc.skill_registry.list_skills()
    panel._evolve_looks()
    qapp.processEvents()
    assert svc.asset_pipeline.appearance.revision >= 1
    panel._code_draft()
    qapp.processEvents()
    assert svc.list_code_bundles()
    panel.refresh()
    assert panel.skills_table.rowCount() >= 1
    assert panel.log_table.rowCount() >= 1


def test_catalog_generative_register():
    svc = DesktopService.create()
    cat = svc.module_catalog()
    assert any(c["catalog_id"] == "generative_organism" for c in cat)
    result = svc.register_catalog_module("generative_organism")
    assert result["module_id"] == "generative_organism"
    mods = svc.list_modules()
    entry = next(m for m in mods if m["module_id"] == "generative_organism")
    assert entry.get("may_actuate") in (False, None) or entry["may_actuate"] is False
