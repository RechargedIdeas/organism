"""Bio / wet-lab actuation must be hard-refused from the UI service layer."""
from __future__ import annotations

import pytest

from organism_desktop.service import ActuationRefused, DesktopService


def test_request_bio_actuation_raises():
    svc = DesktopService.create()
    with pytest.raises(ActuationRefused, match="hard-refuses"):
        svc.request_bio_actuation(module_id="bio_digital.slime_mold", voltage=1.0)


def test_try_bio_actuation_refused_payload():
    svc = DesktopService.create()
    out = svc.try_bio_actuation(module_id="bio_digital.mycelium")
    assert out["refused"] is True
    assert out["may_actuate"] is False


def test_bio_modules_may_actuate_false():
    svc = DesktopService.create()
    status = svc.bio_status()
    assert status["control_actuation_default"] is False
    assert status["safety_policy"]["actuation_certified"] is False
    for m in status["modules"]:
        assert m["may_actuate"] is False
        assert m["exploration_only"] is True


def test_registry_badges_for_bio():
    svc = DesktopService.create()
    bio = [m for m in svc.list_modules() if m["module_id"].startswith("bio_digital.")]
    assert len(bio) >= 2
    assert all(m["may_actuate"] is False for m in bio)


def test_bio_twin_refresh_ok():
    svc = DesktopService.create()
    twin = svc.refresh_bio_twin()
    assert twin.get("ok") is True
    assert "telemetry" in twin or "sample" in twin
    status = svc.bio_status()
    assert status["hal_available"] is True
    assert status["twin"].get("ok") is True


def test_panel_actuate_button_path_refuses():
    """Mirror BioPanel._actuate path."""
    svc = DesktopService.create()
    result = svc.try_bio_actuation(module_id="bio_digital.slime_mold", voltage=0.5)
    assert result["refused"] is True
