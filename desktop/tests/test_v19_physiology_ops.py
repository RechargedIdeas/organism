"""v1.9 Desktop physiology / ops / docs audit surfaces."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from organism_desktop.service import DesktopService, DESKTOP_VERSION


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def service():
    return DesktopService.create()


def test_desktop_version_19():
    assert DESKTOP_VERSION.startswith("1.9")


def test_physiology_snapshot_deep(service):
    snap = service.physiology_snapshot()
    for key in ("immune", "autonomic", "circadian", "apoptosis", "learned_ise", "morphogenesis", "v02_sink_attached"):
        assert key in snap
    assert snap["v02_sink_attached"] is True
    assert snap["product_limits"]["bio_actuation"] is False


def test_physiology_demos(service):
    assert service.immune_demo()["ok"]
    assert service.autonomic_demo(mode="SYMPATHETIC")["ok"]
    assert service.circadian_demo(steps=2)["ok"]
    assert service.apoptosis_status()["ok"]
    assert service.morphogenesis_demo()["ok"]
    ise = service.learned_ise_demo(promote=False)
    assert ise["ok"]
    assert ise["may_actuate"] is False


def test_multiprocess_ops(service):
    r = service.run_multiprocess_stub(n=2)
    assert r["ok"] and r["label"] == "not_production_bft"


def test_docs_links_include_audit(service):
    titles = [d["title"] for d in service.docs_links()]
    assert any("Audit" in t for t in titles)
    assert any("v1.9" in t or "Generative" in t for t in titles)


def test_physiology_panel_widgets(qapp, service):
    from PySide6.QtWidgets import QPushButton, QLabel
    from organism_desktop.panels.physiology import PhysiologyPanel

    panel = PhysiologyPanel(service)
    assert panel.level_badge.objectName() == "physio_level_badge"
    for name in (
        "physio_immune_demo",
        "physio_autonomic_demo",
        "physio_circadian_demo",
        "physio_apoptosis_status",
        "physio_ise_demo",
        "physio_morphogenesis_demo",
    ):
        child = panel.findChild(QPushButton, name)
        assert child is not None, f"missing button {name}"
    assert hasattr(panel, "_immune")
    panel._immune()
    panel._autonomic()
    panel._circadian()


def test_ops_multiprocess_button(qapp, service):
    from organism_desktop.panels.ops import OpsPanel

    panel = OpsPanel(service)
    assert hasattr(panel, "_multiprocess")
    panel._multiprocess()


def test_organism_replay_and_hv(qapp, service):
    from organism_desktop.panels.organism import OrganismPanel
    from organism_desktop.panels.workspace import WorkspacePanel

    # seed a draft
    service.evolve_organism_code("replay seed intent", auto_promote=False)
    org = OrganismPanel(service)
    org._refresh_replays()
    entries = service.list_draft_replays()
    assert isinstance(entries, list)
    hv = service.hypervector_preview(seed=7)
    assert "sparkline" in hv
    ws = WorkspacePanel(service)
    ws._hv()
