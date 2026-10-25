"""v15:desktop — blocking gate for Organism Desktop control plane (deepened)."""
from __future__ import annotations

from organism_desktop.nav import panel_ids
from organism_desktop.service import ActuationRefused, DESKTOP_VERSION, DesktopService


def test_v15_desktop_gate():
    """Gate: ten panels, CPU home, pipeline, registry, physiology, traces, bio refuse."""
    assert panel_ids() == [
        "home",
        "registry",
        "workspace",
        "pipelines",
        "physiology",
        "metamodel",
        "bio",
        "traces",
        "ops",
        "docs",
    ]
    assert DESKTOP_VERSION == "1.5.2"
    svc = DesktopService.create()
    st = svc.home_status()
    assert st["cpu_everywhere"] is True
    assert st["device"]["runtime"] == "CPU_GENERAL"
    assert st["desktop_version"] == "1.5.2"

    # Registry round-trip
    reg = svc.register_core_module("deterministic")
    assert reg["registered"] is True
    assert any(m["module_id"] == "deterministic_engine" for m in svc.list_modules())

    # Workspace bind/unbind
    wrote = svc.write_demo_binding()
    assert svc.unbind_binding(wrote["binding_id"])["unbound"] is True

    # Pipeline
    plan = svc.run_pipeline(task_id="gate-pipeline")
    assert plan.disposition
    assert plan.plan["plan_id"]

    # Physiology demo
    demo = svc.simulate_l0_to_l1()
    assert demo["ok"] is True and demo["level"] == "L1"
    svc.reset_physiology_demo()

    # Traces
    emit = svc.emit_demo_traces()
    assert emit["emitted"] >= 1
    assert svc.list_traces(kind="Routing")

    # Bio twin + refuse
    twin = svc.refresh_bio_twin()
    assert twin.get("ok") is True
    try:
        svc.request_bio_actuation()
        raise AssertionError("bio actuation must refuse")
    except ActuationRefused:
        pass

    assert svc.ops_info()["validate"]["ok"] is True
    parity = svc.status_parity()
    assert parity["cpu_everywhere"] is True
    assert parity["device_runtime"] == "CPU_GENERAL"
    soak = svc.soak_snapshot()
    assert soak["runbook_exists"] is True
    assert svc.refresh_bundle()["ok"] is True
