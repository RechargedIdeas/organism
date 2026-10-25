"""Contract / assert service + last results."""
from __future__ import annotations

from organism_desktop.service import DesktopService


def test_run_contract_checks_stores_last():
    svc = DesktopService.create()
    assert svc.last_contract_results() == []
    results = svc.run_contract_checks()
    assert results
    assert svc.last_contract_results() == results
    assert all("module_id" in r for r in results)
    assert all("ok" in r for r in results)
    # Core modules should validate cleanly
    by_id = {r["module_id"]: r for r in results}
    assert by_id["deterministic_engine"]["ok"] is True
    assert by_id["deterministic_engine"]["may_actuate"] is True
    # Bio exploration modules present with RESEARCH badge
    bio = [r for r in results if r.get("bio_exploration") or "bio_digital" in r["module_id"]]
    assert bio
    assert all(r.get("may_actuate") is False for r in bio)


def test_contract_checks_after_catalog_register():
    svc = DesktopService.create()
    svc.register_catalog_module("neurosymbolic")
    results = svc.run_contract_checks()
    ids = {r["module_id"] for r in results}
    assert "neurosymbolic" in ids
    assert next(r for r in results if r["module_id"] == "neurosymbolic")["ok"] is True
