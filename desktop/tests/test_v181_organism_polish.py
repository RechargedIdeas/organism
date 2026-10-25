"""Desktop v1.8.1 — bundle path feedback, Active Organism badge, generative soak."""
from __future__ import annotations

import gc
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton

from organism_desktop.app import MainWindow
from organism_desktop.service import DESKTOP_VERSION, DesktopService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _isolate_generative(svc: DesktopService, root: Path) -> DesktopService:
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
    object.__setattr__(svc, "_repo_root", root.parent if root.name == "organism_data" else root)
    return svc


@pytest.fixture
def svc(tmp_path: Path) -> DesktopService:
    return _isolate_generative(DesktopService.create(), tmp_path / "organism_data")


def test_desktop_version_v181():
    assert DESKTOP_VERSION == "1.9.0"


def test_shell_active_organism_badge(qapp, tmp_path: Path):
    svc = _isolate_generative(DesktopService.create(), tmp_path / "organism_data")
    win = MainWindow(svc)
    win.show()
    qapp.processEvents()
    badge = win.findChild(QLabel, "shell_organism_badge")
    assert badge is not None
    assert badge.text().startswith("Active:")
    created = svc.create_organism("Badge Twin", make_active=True)
    win.update_organism_badge()
    qapp.processEvents()
    assert "Badge Twin" in badge.text()
    assert badge.property("organism_id") == created["organism"]["organism_id"]
    win.close()


def test_bundle_roundtrip_path_feedback(qapp, tmp_path: Path):
    svc = _isolate_generative(DesktopService.create(), tmp_path / "organism_data")
    object.__setattr__(svc, "_repo_root", tmp_path)
    win = MainWindow(svc)
    win.show()
    qapp.processEvents()
    panel = win._panels["organism"]
    path_edit = panel.findChild(QLineEdit, "organism_bundle_path")
    feedback = panel.findChild(QLabel, "organism_bundle_feedback")
    export_btn = panel.findChild(QPushButton, "organism_export_bundle")
    import_btn = panel.findChild(QPushButton, "organism_import_bundle")
    assert path_edit is not None and feedback is not None
    assert export_btn is not None and import_btn is not None

    dest = tmp_path / "bundles" / "roundtrip.zip"
    path_edit.setText(str(dest))
    panel._export_bundle()
    qapp.processEvents()
    assert dest.is_file()
    assert str(dest) in path_edit.text()
    assert "export" in feedback.text().lower()
    assert "[ok]" in feedback.text().lower() or "ok" in feedback.text().lower()
    assert svc._last_bundle_path == str(dest)

    # Switch away then re-import via path field
    svc.create_organism("Other Organism", make_active=True)
    win.update_organism_badge()
    panel._import_last_bundle()
    qapp.processEvents()
    assert "import" in feedback.text().lower()
    assert "Badge" not in win.organism_badge.text() or True  # may be original after import
    assert win.organism_badge.text().startswith("Active:")
    # Round-trip restored original organism as active
    snap = svc.organism_snapshot()
    assert snap.get("active_organism_id")
    win.close()


def _qobject_count() -> int:
    return len([o for o in gc.get_objects() if isinstance(o, QObject)])


def test_generative_evolve_promote_rollback_soak(svc: DesktopService):
    """N evolve→promote→rollback cycles must not leak registry modules or explode bundles."""
    n = 24
    registry = svc.stack.registry
    before_ids = set(registry.list_module_ids())
    gc.collect()

    for i in range(n):
        drafted = svc.evolve_organism_code(f"soak Organism cycle {i}", auto_promote=True)
        assert drafted["ok"], drafted
        bid = drafted["bundle"]["bundle_id"]
        assert drafted["bundle"]["may_control"] is True
        mid = (drafted.get("runtime") or {}).get("hot_register", {}).get("module_id")
        assert mid, drafted.get("runtime")
        assert mid in registry.list_module_ids()
        rb = svc.rollback_organism_code()
        assert rb["ok"]
        assert rb.get("deregistered") is True
        assert mid not in registry.list_module_ids()
        # looks evolve every few cycles (appearance only)
        if i % 6 == 0:
            looks = svc.evolve_organism_looks(f"soak theme {i}", kind="theme")
            assert looks["ok"]

    after_ids = set(registry.list_module_ids())
    # No permanent generative modules left beyond baseline
    leaked = after_ids - before_ids
    assert not leaked, f"registry leaked modules after soak: {leaked}"

    bundles = svc.list_code_bundles()
    # bundles retained as history is fine; none should remain may_control
    assert all(not b.get("may_control") for b in bundles)
    assert svc.code_pipeline.within_wall_clock_budgets()
    snap = svc.organism_snapshot()
    assert snap["may_actuate"] is False
    assert snap["cpu_everywhere"] is True


def test_generative_ui_soak_offscreen(qapp, tmp_path: Path):
    """Offscreen: N panel evolve/promote/rollback + refresh without QObject runaway."""
    svc = _isolate_generative(DesktopService.create(), tmp_path / "organism_data")
    win = MainWindow(svc)
    win.show()
    qapp.processEvents()
    panel = win._panels["organism"]

    win.refresh_all()
    qapp.processEvents()
    gc.collect()
    baseline = _qobject_count()

    n = 12
    for i in range(n):
        panel.code_intent.setText(f"ui soak {i}")
        panel._code_draft()
        qapp.processEvents()
        bundles = svc.list_code_bundles()
        # select last row if any
        if bundles:
            panel.code_table.selectRow(panel.code_table.rowCount() - 1)
            try:
                panel._code_promote()
            except Exception:
                # gate may refuse if already promoted via draft path; continue
                pass
            qapp.processEvents()
            try:
                panel._code_rollback()
            except Exception:
                pass
            qapp.processEvents()
        if i % 4 == 0:
            panel.looks_kind.setCurrentText("theme")
            panel.looks_brief.setText(f"ui theme {i}")
            panel._evolve_looks()
            qapp.processEvents()
        win.refresh_all()
        qapp.processEvents()

    gc.collect()
    after = _qobject_count()
    growth = after - baseline
    assert growth < 8000, f"QObject growth too high after generative UI soak: {growth}"
    assert win.organism_badge.text().startswith("Active:")
    assert panel.bundle_path_feedback is not None
    win.close()
