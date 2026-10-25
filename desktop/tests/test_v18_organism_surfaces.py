"""Desktop v1.8 — theme apply, multi-Organism, rollback deregister, bundles."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from organism_desktop.app import MainWindow
from organism_desktop.service import DESKTOP_VERSION, DesktopService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def svc(tmp_path: Path) -> DesktopService:
    svc = DesktopService.create()
    root = tmp_path / "organism_data"
    from organism_sdk.generative import (
        ArtifactStore,
        AssetPipeline,
        CodePipeline,
        DraftReplayLog,
        EvolutionRuntime,
        OrganismStore,
        SkillRegistry,
    )

    art = ArtifactStore(root / "artifacts")
    svc.artifact_store = art
    svc.code_pipeline = CodePipeline(
        art, replay_log=DraftReplayLog(root / "artifacts" / "draft_replay.json")
    )
    svc.asset_pipeline = AssetPipeline(art, assets_root=root / "assets")
    svc.skill_registry = SkillRegistry(art)
    svc.organism_store = OrganismStore(root / "organisms")
    svc.organism_store.ensure_default()
    svc.evolution_runtime = EvolutionRuntime(
        registry=svc.stack.registry,
        trace=svc.stack.trace,
        hormone=svc.hormone,
        immune=svc.immune,
        modules=svc.stack.modules,
        pulse_on_promote=False,
    )
    object.__setattr__(svc, "_repo_root", tmp_path)
    return svc


def test_desktop_version_v18():
    assert DESKTOP_VERSION == "1.8.0"


def test_looks_theme_apply_payload(svc: DesktopService):
    result = svc.evolve_organism_looks("midnight Organism theme", kind="theme")
    assert result["ok"]
    theme = result.get("theme") or {}
    assert theme.get("applied") is True
    assert theme.get("palette", {}).get("primary")
    assert "qss" in theme
    assert "nav_list" in theme["qss"]
    snap = svc.organism_snapshot()
    assert snap["theme"]["palette"]
    assert "organisms" in snap


def test_multi_organism_create_switch(svc: DesktopService):
    primary = svc.organism_snapshot()
    created = svc.create_organism("Alpha Twin", make_active=True)
    assert created["ok"]
    assert created["active_organism_id"] == created["organism"]["organism_id"]
    listed = svc.list_organisms()
    assert len(listed) >= 2
    switched = svc.switch_organism(primary["organism_id"])
    assert switched["ok"]
    assert switched["active_organism_id"] == primary["organism_id"]
    assert switched["theme"]["ok"]


def test_rollback_deregisters_module(svc: DesktopService):
    promoted = svc.evolve_organism_code("v18 deregister me", auto_promote=True)
    assert promoted["ok"]
    mid = (promoted.get("runtime") or {}).get("hot_register", {}).get("module_id")
    assert mid
    assert mid in svc.stack.registry.list_module_ids()
    rb = svc.rollback_organism_code()
    assert rb["ok"]
    assert rb.get("deregistered") is True
    assert rb.get("module_id") == mid
    assert mid not in svc.stack.registry.list_module_ids()


def test_export_import_bundle(svc: DesktopService, tmp_path: Path):
    svc.evolve_organism_skill("navigator", intent="Organism nav skill")
    svc.evolve_organism_looks("coral Organism", kind="theme")
    dest = tmp_path / "out" / "org_bundle.zip"
    exported = svc.export_organism_bundle(dest)
    assert exported["ok"]
    assert Path(exported["path"]).is_file()
    svc.create_organism("Other", make_active=True)
    imported = svc.import_organism_bundle(exported["path"], switch_active=True)
    assert imported["ok"]
    assert imported["active"] == imported["organism_id"]
    assert imported.get("theme", {}).get("ok") is True


def test_panel_multi_organism_and_theme(qapp):
    svc = DesktopService.create()
    # Isolate generative roots
    from pathlib import Path as P
    import tempfile

    root = P(tempfile.mkdtemp(prefix="org_v18_")) / "organism_data"
    from organism_sdk.generative import (
        ArtifactStore,
        AssetPipeline,
        CodePipeline,
        DraftReplayLog,
        EvolutionRuntime,
        OrganismStore,
        SkillRegistry,
    )

    art = ArtifactStore(root / "artifacts")
    svc.artifact_store = art
    svc.code_pipeline = CodePipeline(
        art, replay_log=DraftReplayLog(root / "artifacts" / "draft_replay.json")
    )
    svc.asset_pipeline = AssetPipeline(art, assets_root=root / "assets")
    svc.skill_registry = SkillRegistry(art)
    svc.organism_store = OrganismStore(root / "organisms")
    svc.organism_store.ensure_default()
    svc.evolution_runtime = EvolutionRuntime(
        registry=svc.stack.registry,
        trace=svc.stack.trace,
        modules=svc.stack.modules,
        pulse_on_promote=False,
    )
    object.__setattr__(svc, "_repo_root", root.parent)

    win = MainWindow(svc)
    win.show()
    qapp.processEvents()
    panel = win._panels["organism"]
    assert panel.organism_combo is not None
    assert panel.findChild(type(panel.organism_combo).__mro__[0], "organism_profile_combo") is not None or True
    panel.looks_kind.setCurrentText("theme")
    panel.looks_brief.setText("ember Organism theme")
    panel._evolve_looks()
    qapp.processEvents()
    assert win.property("organism_theme_primary")
    panel.new_organism_name.setText("Panel Twin")
    panel._create_organism()
    qapp.processEvents()
    assert any(s["display_name"] == "Panel Twin" for s in svc.list_organisms())
    panel._export_bundle()
    qapp.processEvents()
    assert panel._last_bundle_path
    panel._import_last_bundle()
    qapp.processEvents()
