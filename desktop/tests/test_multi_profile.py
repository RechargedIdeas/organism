"""Multi-profile deploy switch + status_facts delta."""
from __future__ import annotations

from organism_desktop.service import DesktopService


def test_list_profiles_includes_cpu_only_and_default():
    svc = DesktopService.create()
    profiles = svc.list_deploy_profiles()
    names = {p["name"] for p in profiles if p.get("ok")}
    assert "cpu_only" in names
    assert "default" in names
    active = [p for p in profiles if p.get("active")]
    assert len(active) == 1
    assert active[0]["name"] == "cpu_only"
    assert active[0]["health_port"] == 8787


def test_switch_profile_changes_status_facts():
    svc = DesktopService.create()
    before = svc.status_parity()
    assert before["profile"] == "cpu_only"
    assert before["health_port"] == 8787
    result = svc.switch_deploy_profile("default")
    assert result["ok"] is True
    assert result["profile"] == "default"
    assert result["after"]["health_port"] == 8788
    assert result["delta"]["profile"]["before"] == "cpu_only"
    assert result["delta"]["profile"]["after"] == "default"
    assert result["delta"]["health_port"]["after"] == 8788
    assert svc.status_parity()["cpu_everywhere"] is True
    # Switch back
    back = svc.switch_deploy_profile("cpu_only")
    assert back["profile"] == "cpu_only"
    assert svc.status_parity()["health_port"] == 8787


def test_ops_info_exposes_profiles():
    svc = DesktopService.create()
    info = svc.ops_info()
    assert info["active_profile"] == "cpu_only"
    assert any(p["name"] == "default" for p in info["profiles"])
