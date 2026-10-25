"""Desktop ↔ CLI parity: shared status_facts keys must match."""
from __future__ import annotations

from organism_sdk.deploy.config import default_cpu_only_config
from organism_sdk.deploy.stack import build_minimal_stack
from organism_sdk.deploy.status_facts import PARITY_KEYS, common_status_facts, enrich_cli_status
from organism_desktop.service import DesktopService


def test_parity_keys_stable():
    assert "cpu_everywhere" in PARITY_KEYS
    assert "organism_version" in PARITY_KEYS
    assert "device_runtime" in PARITY_KEYS
    assert "profile" in PARITY_KEYS


def test_cli_enrich_includes_parity_keys():
    stack = build_minimal_stack(default_cpu_only_config())
    enriched = enrich_cli_status(stack)
    for k in PARITY_KEYS:
        assert k in enriched, k
    assert enriched["cpu_everywhere"] is True
    assert enriched["device_runtime"] == "CPU_GENERAL"
    assert enriched["prefer_gpu"] is False
    assert enriched["ok"] is True


def test_desktop_cli_parity_matches_fresh_stack():
    """Desktop status_parity agrees with CLI enrich on same DeployConfig.

    Desktop registers bio modules (exploration-only); parity keys are
    config/device-derived and must still match a fresh MinimalStack.
    """
    cfg = default_cpu_only_config()
    cli_stack = build_minimal_stack(cfg)
    cli = enrich_cli_status(cli_stack)
    svc = DesktopService.create(cfg)
    desktop = svc.status_parity()
    for k in PARITY_KEYS:
        assert desktop[k] == cli[k], f"parity drift on {k}: desktop={desktop[k]!r} cli={cli[k]!r}"


def test_home_status_embeds_cli_parity_and_soak():
    svc = DesktopService.create()
    st = svc.home_status()
    assert st["cpu_everywhere"] is True
    assert "cli_parity" in st
    assert st["cli_parity"]["device_runtime"] == "CPU_GENERAL"
    assert "soak" in st
    soak = st["soak"]
    assert soak.get("runbook_exists") is True
    assert soak.get("script_exists") is True
    # Short soak should succeed when harness is importable (pytest root).
    assert soak.get("ok") is True
    assert soak.get("reconstructible") is True


def test_ops_info_deploy_and_soak_paths():
    ops = DesktopService.create().ops_info()
    assert ops["cpu_everywhere"] is True
    assert ops["deploy_profile"]
    assert ops["deploy_config_exists"] is True
    assert ops["soak_runbook_exists"] is True
    assert ops["soak_script_exists"] is True
    assert ops["validate"]["ok"] is True
    assert ops["cli_parity"]["cpu_everywhere"] is True
