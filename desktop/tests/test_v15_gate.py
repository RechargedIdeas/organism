"""v15:desktop — blocking gate for Organism Desktop control plane."""
from __future__ import annotations

from organism_desktop.nav import panel_ids
from organism_desktop.service import ActuationRefused, DesktopService


def test_v15_desktop_gate():
    """Gate: ten panels, CPU home, pipeline decide, bio refuse."""
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
    svc = DesktopService.create()
    st = svc.home_status()
    assert st["cpu_everywhere"] is True
    assert st["device"]["runtime"] == "CPU_GENERAL"
    plan = svc.run_pipeline()
    assert plan.disposition
    assert plan.plan["plan_id"]
    try:
        svc.request_bio_actuation()
        raise AssertionError("bio actuation must refuse")
    except ActuationRefused:
        pass
    assert svc.ops_info()["validate"]["ok"] is True
