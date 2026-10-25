"""v15/v16 desktop gate — blocking gate for Organism Desktop control plane."""
from __future__ import annotations

from organism_desktop.nav import panel_ids
from organism_desktop.service import ActuationRefused, DESKTOP_VERSION, DesktopService


def test_v15_desktop_gate():
    """Gate: twelve panels, CPU home, catalog, pipeline inspector, contracts, bio refuse."""
    assert panel_ids() == [
        "home",
        "registry",
        "catalog",
        "workspace",
        "pipelines",
        "physiology",
        "metamodel",
        "bio",
        "traces",
        "contracts",
        "ops",
        "docs",
    ]
    assert DESKTOP_VERSION == "1.6.1"
    svc = DesktopService.create()
    st = svc.home_status()
    assert st["cpu_everywhere"] is True
    assert st["device"]["runtime"] == "CPU_GENERAL"
    assert st["desktop_version"] == "1.6.1"

    # Registry round-trip
    reg = svc.register_core_module("deterministic")
    assert reg["registered"] is True
    assert any(m["module_id"] == "deterministic_engine" for m in svc.list_modules())

    # Catalog RESEARCH_TIER present
    cat = svc.module_catalog()
    assert any(c["research_tier"] for c in cat)
    assert any(c["catalog_id"] == "physical_research" for c in cat)

    # Workspace bind/unbind
    wrote = svc.write_demo_binding()
    assert svc.unbind_binding(wrote["binding_id"])["unbound"] is True

    # Pipeline + plan inspector
    plan = svc.run_pipeline(task_id="gate-pipeline")
    assert plan.disposition
    assert plan.plan["plan_id"]
    insp = svc.inspect_plan()
    assert insp["ok"] is True
    assert insp["summary"]["task_id"] == "gate-pipeline"

    # Physiology demo
    demo = svc.simulate_l0_to_l1()
    assert demo["ok"] is True and demo["level"] == "L1"
    svc.reset_physiology_demo()

    # Traces + export jump
    emit = svc.emit_demo_traces()
    assert emit["emitted"] >= 1
    assert svc.list_traces(kind="Routing")
    jump = svc.traces_for_last_pipeline()
    assert jump["ok"] is True

    # Contracts
    checks = svc.run_contract_checks()
    assert checks
    assert svc.last_contract_results()

    # Multi-profile
    profiles = {p["name"] for p in svc.list_deploy_profiles() if p.get("ok")}
    assert "cpu_only" in profiles and "default" in profiles
    switched = svc.switch_deploy_profile("default")
    assert switched["profile"] == "default"
    assert switched["after"]["health_port"] == 8788

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
    assert parity["profile"] == "default"
    soak = svc.soak_snapshot()
    assert soak["runbook_exists"] is True
    # v1.6.1: hormone timeline, drillbook, rust, soak harness
    ht = svc.run_hormone_timeline(windows=4)
    assert ht["ok"] is True and len(ht["rows"]) == 4
    drill = svc.run_degradation_drillbook(confirm=True, target="L2")
    assert drill["ok"] is True and drill["level"] == "L2"
    svc.reset_physiology_demo()
    fed = svc.run_federation_stub()
    assert fed["stub_only"] is True and fed["not_production_bft"] is True
    rust = svc.rust_runtime_status(probe_cargo=False)
    assert rust["read_only"] is True and rust["crates_present"] >= 1
    soak = svc.run_short_soak_harness(windows=4)
    assert soak["ok"] is True and soak["result_path"]
    assert svc.refresh_bundle()["ok"] is True
