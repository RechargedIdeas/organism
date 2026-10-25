"""v1.4 deploy config + smoke."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from organism_sdk.deploy.config import (
    DeployConfigError,
    load_deploy_config,
    validate_deploy_config,
)
from organism_sdk.deploy.serve import serve_stack
from organism_sdk.deploy.stack import build_minimal_stack
from organism_sdk.cli import main

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "deploy" / "config" / "cpu_only.yaml"


def test_load_cpu_only_yaml():
    cfg = load_deploy_config(CFG)
    assert cfg.profile == "cpu_only"
    assert cfg.runtime.prefer_gpu is False
    assert cfg.health.port == 8787
    assert validate_deploy_config(cfg) == []


def test_default_config_validates():
    cfg = load_deploy_config(None)
    assert cfg.profile == "cpu_only"
    assert validate_deploy_config(cfg) == []


def test_invalid_port():
    cfg = load_deploy_config(CFG)
    cfg.health.port = 99999
    issues = validate_deploy_config(cfg)
    assert any("port" in i for i in issues)


def test_missing_config_raises():
    with pytest.raises(DeployConfigError):
        load_deploy_config("/nonexistent/organism.yaml")


def test_build_minimal_stack_registers_modules():
    cfg = load_deploy_config(CFG)
    stack = build_minimal_stack(cfg)
    st = stack.status()
    assert st["ok"] is True
    assert st["module_count"] >= 2
    assert st["device"]["runtime"] == "CPU_GENERAL"
    assert stack.health_report().status == "HEALTHY"


def test_serve_dry_run():
    cfg = load_deploy_config(CFG)
    result = serve_stack(cfg, dry_run=True)
    assert result["dry_run"] is True
    assert result["listening"] is False
    assert result["module_count"] >= 2


def test_serve_once_ephemeral_port():
    import urllib.request

    cfg = load_deploy_config(CFG)
    result = serve_stack(cfg, dry_run=False, port=0)
    assert result["listening"] is True
    server = result["_server"]
    try:
        url = result["health_url"]
        with urllib.request.urlopen(url, timeout=2) as resp:
            body = json.loads(resp.read().decode())
        assert body["status"] == "HEALTHY"
        status_url = url.replace("/health", "/status")
        with urllib.request.urlopen(status_url, timeout=2) as resp:
            st = json.loads(resp.read().decode())
        assert st["ok"] is True
    finally:
        server.shutdown()


def test_cli_validate_config():
    assert main(["validate-config", "-c", str(CFG)]) == 0


def test_cli_status():
    assert main(["status", "-c", str(CFG)]) == 0


def test_cli_serve_dry_run():
    assert main(["serve", "-c", str(CFG), "--dry-run"]) == 0


def test_cli_status_enrichment(capsys):
    """organism status JSON includes shared parity keys (cpu_everywhere, etc.)."""
    from organism_sdk.deploy.status_facts import PARITY_KEYS

    rc = main(["status", "-c", str(CFG)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    for k in PARITY_KEYS:
        assert k in out, k
    assert out["cpu_everywhere"] is True
    assert out["device_runtime"] == "CPU_GENERAL"
    assert out["profile"] == "cpu_only"


def test_load_default_yaml():
    cfg = load_deploy_config(ROOT / "deploy" / "config" / "default.yaml")
    assert cfg.profile == "default"
    assert cfg.runtime.prefer_gpu is False
    assert cfg.health.port == 8788
    assert validate_deploy_config(cfg) == []
