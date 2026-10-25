"""v1.7 / v1.7.2 Organism Evolution Desktop surfaces."""
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
    assert DESKTOP_VERSION.startswith("1.")
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


def test_service_rollback_pack_dag_preview():
    svc = DesktopService.create()
    a = svc.evolve_organism_code("rollback A", auto_promote=True)
    b = svc.evolve_organism_code("rollback B", auto_promote=True)
    assert b["bundle"]["may_control"] is True
    rb = svc.rollback_organism_code()
    assert rb["bundle"]["stage"] == "ROLLBACK"
    assert rb["bundle"]["may_control"] is False
    prog = svc.code_stage_progress(a["bundle"]["bundle_id"])
    assert prog["stage"] == "PROMOTED"
    pack = svc.evolve_organism_looks_pack("desktop pack Organism")
    assert pack["ok"]
    assert pack["appearance"]["pack_id"]
    aid = pack["appearance"]["avatar_id"]
    prev = svc.organism_asset_preview(aid)
    assert prev["preview_text"]
    skill = svc.evolve_organism_skill("dag_base", intent="base", auto_promote=False)
    svc.promote_organism_skill(skill["skill"]["skill_id"])
    improved = svc.improve_organism_skill_from_trace(skill["skill"]["skill_id"])
    assert improved["ok"]
    dag = svc.organism_skill_dag()
    assert "nodes" in dag and "edges" in dag


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
    # promote then rollback via panel
    bundles = svc.list_code_bundles()
    ready = [b for b in bundles if (b.get("gate") or {}).get("ready")]
    if ready:
        # select first row by promoting via service then panel rollback
        svc.promote_organism_code(ready[0]["bundle_id"])
    panel._code_rollback()
    qapp.processEvents()
    panel.refresh()
    assert panel.skills_table.rowCount() >= 1
    assert panel.log_table.rowCount() >= 1
    assert panel.stage_bar.value() >= 0
    assert panel.skill_dag.toPlainText()


def test_catalog_generative_register():
    svc = DesktopService.create()
    cat = svc.module_catalog()
    assert any(c["catalog_id"] == "generative_organism" for c in cat)
    result = svc.register_catalog_module("generative_organism")
    assert result["module_id"] == "generative_organism"
    mods = svc.list_modules()
    entry = next(m for m in mods if m["module_id"] == "generative_organism")
    assert entry.get("may_actuate") in (False, None) or entry["may_actuate"] is False


def test_e2e_evolve_improve_promote_appears_in_catalog():
    """v1.7.2: evolve skill → improve from trace → promote → appear in catalog."""
    assert DESKTOP_VERSION.startswith("1.")
    svc = DesktopService.create()
    # 1. Evolve skill (shadow scored, not auto-promoted)
    gen = svc.evolve_organism_skill(
        "catalog_evolver",
        intent="Organism signal analyst for catalog e2e",
        auto_promote=False,
    )
    assert gen["ok"]
    skill_id = gen["skill"]["skill_id"]
    assert gen["bundle"]["stage"] == "SHADOW_SCORED"
    assert gen.get("within_budgets") is True

    # 2. Improve from evolution_log / traces
    improved = svc.improve_organism_skill_from_trace(skill_id, auto_promote=False)
    assert improved["ok"]
    assert "from_trace" in improved["skill"]["tags"]
    assert improved["skill"]["version"] != gen["skill"]["version"]

    # 3. Promote → hot-register into ModuleRegistry + catalog
    promoted = svc.promote_organism_skill(skill_id)
    assert promoted["ok"]
    assert promoted["skill"]["may_control"] is True
    runtime = promoted.get("runtime") or {}
    hot = runtime.get("hot_register")
    assert hot is not None
    assert hot["module_id"].startswith("gen_")
    assert hot["may_actuate"] is False
    assert "EXPLORATION" in hot["shadow_gate"] or hot["state"] == "EXPLORATION"

    # 4. Appear in Desktop module catalog (dynamic generative entry)
    cat = svc.module_catalog()
    match = [c for c in cat if c.get("module_id") == hot["module_id"]]
    assert match, f"hot-registered module missing from catalog: {hot['module_id']}"
    assert match[0].get("generative") is True
    assert match[0].get("registered") is True
    assert match[0].get("may_actuate_declared") is False

    # 5. Evolution traces emitted
    traces = svc.list_traces(limit=200, kind="Evolution")
    assert traces, "expected EvolutionTraceEntry in TraceEmitter"
    evo_kinds = {t.get("evolution_kind") or "" for t in traces}
    assert (
        any("promote" in str(k).lower() for k in evo_kinds)
        or any("Hot-registered" in str(t.get("summary") or "") for t in traces)
    )

    # 6. Hormone pulse optional — dopamine should have moved if HormoneBus present
    if svc.hormone is not None and runtime.get("hormone_pulse"):
        assert runtime["hormone_pulse"]["dopamine"] > 0.0

    # 7. Registered in stack modules
    assert hot["module_id"] in svc.stack.modules
    assert hot["module_id"] in svc.stack.registry.list_module_ids()


def test_immune_quarantine_via_desktop_reject():
    svc = DesktopService.create()
    assert svc.evolution_runtime is not None
    assert svc.immune is not None

    class Bad:
        name = "desktop_bad"

        def draft(self, intent, *, spec=None):
            return "import os\ndef main():\n    return os.getcwd()\n"

    # Drive reject through code pipeline then after_reject
    raw = svc.code_pipeline.evolve("hack", backend=Bad(), auto_promote=False)  # type: ignore[arg-type]
    assert raw.stage.value == "REJECTED"
    meta = svc.evolution_runtime.after_reject(
        raw, code_pipeline=svc.code_pipeline, organism_id="organism_primary"
    )
    assert meta["quarantine"] is not None
    assert meta["quarantine"]["demoted"] is True
