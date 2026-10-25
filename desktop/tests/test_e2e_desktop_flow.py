"""End-to-end DesktopService flow: register → bind → decide → traces → L0→L1."""
from __future__ import annotations

from organism_desktop.service import ActuationRefused, DesktopService


def test_e2e_register_bind_decide_trace_degrade():
    svc = DesktopService.create()
    assert svc.degrade.level == "L0"

    # 1. Register modules
    det = svc.register_core_module("deterministic")
    learned = svc.register_core_module("learned")
    assert det["registered"] and learned["registered"]
    ids = {m["module_id"] for m in svc.list_modules()}
    assert "deterministic_engine" in ids
    assert "learned_module_t2" in ids
    # Bio exploration modules present; may_actuate False
    bio = [m for m in svc.list_modules() if m.get("bio_exploration")]
    assert bio
    assert all(m["may_actuate"] is False for m in bio)

    # 2. Bind workspace
    wrote = svc.write_demo_binding(tag="desktop.e2e")
    bindings = svc.list_bindings()
    assert any(b["binding_id"] == wrote["binding_id"] for b in bindings)

    # 3. Decide task
    plan = svc.run_pipeline(
        form="pattern_recognition",
        safety_tier="medium",
        task_id="e2e-task-1",
        requires_determinism=True,
    )
    assert plan.disposition
    assert plan.plan["task_id"] == "e2e-task-1"
    assert plan.plan["plan_id"]

    # 4. Emit traces
    emit = svc.emit_demo_traces()
    assert emit["emitted"] >= 1
    traces = svc.list_traces()
    assert traces
    assert any("Routing" in t["type"] for t in traces)

    # 5. Degrade L0 → L1
    demo = svc.simulate_l0_to_l1()
    assert demo["ok"] is True
    assert demo["level"] == "L1"
    assert demo["safe"] is True
    phys = svc.physiology_snapshot()
    assert phys["degradation_level"] == "L1"

    # 6. UI service aggregate state
    home = svc.home_status()
    assert home["degradation_level"] == "L1"
    assert home["cpu_everywhere"] is True
    assert home["ok"] is True
    bundle = svc.refresh_bundle()
    assert bundle["ok"] is True
    assert bundle["physiology"]["degradation_level"] == "L1"

    # 7. Actuation still refused after full flow
    refused = svc.try_bio_actuation(module_id="slime_mold")
    assert refused["refused"] is True
    assert refused["may_actuate"] is False
    try:
        svc.request_bio_actuation()
        raise AssertionError("must refuse")
    except ActuationRefused:
        pass

    # Cleanup path
    assert svc.unbind_binding(wrote["binding_id"])["unbound"] is True
    reset = svc.reset_physiology_demo()
    assert reset["level"] == "L0"
