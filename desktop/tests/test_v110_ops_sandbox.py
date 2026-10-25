"""v1.10 Desktop Ops — host kind + native sandbox surfaces."""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from organism_desktop.service import DesktopService


def test_ops_info_includes_host_and_sandbox():
    svc = DesktopService.create()
    info = svc.ops_info()
    assert info["cpu_everywhere"] is True
    assert info.get("docker_required") is False
    assert "host" in info or "host_kind" in info
    assert "sandbox" in info
    assert info["sandbox"]["native"] is True
    assert info["sandbox"]["docker_required"] is False


def test_sandbox_self_check_via_service():
    svc = DesktopService.create()
    result = svc.sandbox_self_check()
    assert result["ok"] is True


def test_list_profiles_includes_bare_vm_container():
    svc = DesktopService.create()
    names = {p["name"] for p in svc.list_deploy_profiles()}
    assert "bare_metal" in names
    assert "vm" in names
    assert "container_generic" in names
