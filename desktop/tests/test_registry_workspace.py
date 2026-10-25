"""Registry register/refresh + workspace bind/unbind via DesktopService."""
from __future__ import annotations

import pytest

from organism_desktop.service import ActuationRefused, DesktopService


def test_register_core_modules_and_list():
    svc = DesktopService.create()
    before = {m["module_id"] for m in svc.list_modules()}
    assert "deterministic_engine" in before
    assert "learned_module_t2" in before

    det = svc.register_core_module("deterministic")
    assert det["registered"] is True
    assert det["module_id"] == "deterministic_engine"

    learn = svc.register_core_module("learned")
    assert learn["registered"] is True
    assert learn["module_id"] == "learned_module_t2"

    ids = {m["module_id"] for m in svc.list_modules()}
    assert "deterministic_engine" in ids
    assert "learned_module_t2" in ids


def test_deregister_core_then_reregister():
    svc = DesktopService.create()
    out = svc.deregister_module("deterministic_engine")
    assert out["deregistered"] is True
    ids = {m["module_id"] for m in svc.list_modules()}
    assert "deterministic_engine" not in ids
    again = svc.register_core_module("deterministic")
    assert again["module_id"] == "deterministic_engine"
    assert again["module_id"] in {m["module_id"] for m in svc.list_modules()}


def test_refuse_bio_deregister():
    svc = DesktopService.create()
    bio = [m for m in svc.list_modules() if m["module_id"].startswith("bio_digital.")]
    assert bio
    with pytest.raises(ActuationRefused):
        svc.deregister_module(bio[0]["module_id"])


def test_workspace_bind_unbind_list():
    svc = DesktopService.create()
    wrote = svc.write_demo_binding(tag="desktop.test")
    bid = wrote["binding_id"]
    bindings = svc.list_bindings()
    assert any(b["binding_id"] == bid for b in bindings)
    assert any("desktop.test" in (b.get("tags") or []) for b in bindings)
    unbound = svc.unbind_binding(bid)
    assert unbound["unbound"] is True
    assert not any(b["binding_id"] == bid for b in svc.list_bindings())
