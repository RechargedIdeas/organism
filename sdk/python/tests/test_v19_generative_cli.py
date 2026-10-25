"""v1.9 generative CLI parity."""
from __future__ import annotations

import json
from pathlib import Path

from organism_sdk.cli import main


def _run(argv, tmp_path: Path, capsys):
    code = main([*argv, "--data-root", str(tmp_path)])
    captured = capsys.readouterr()
    return code, captured.out


def test_list_templates_cli(capsys):
    assert main(["list-templates"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and "scorer" in out["templates"]


def test_evolve_promote_rollback_cli(tmp_path: Path, capsys):
    # Single-process auto-promote exercises gate + hot-register.
    code, out = _run(
        ["evolve-code", "--intent", "Organism CLI scorer", "--auto-promote"],
        tmp_path,
        capsys,
    )
    assert code == 0, out
    evolved = json.loads(out)
    assert evolved["ok"]
    bundle = evolved["bundle"]
    assert bundle["gate"]["sandbox_ok"] is True
    if bundle.get("may_control"):
        assert bundle["stage"] == "PROMOTED"
        code, out = _run(["rollback-code"], tmp_path, capsys)
        assert code == 0, out
        assert json.loads(out)["ok"]
    else:
        # Cross-process promote if evolve left a ready gate without auto-promote path
        bid = bundle["bundle_id"]
        if bundle["gate"].get("ready"):
            code, out = _run(["promote-code", "--bundle-id", bid], tmp_path, capsys)
            assert code == 0, out
            code, out = _run(["rollback-code"], tmp_path, capsys)
            assert code == 0, out

    code, out = _run(["evolve-looks", "--brief", "CLI look", "--kind", "theme"], tmp_path, capsys)
    assert code == 0, out
    assert json.loads(out)["ok"]
    code, out = _run(["evolve-skill", "--name", "cli_nav", "--intent", "navigate"], tmp_path, capsys)
    assert code == 0, out
    assert json.loads(out)["ok"]
    code, out = _run(["list-organisms"], tmp_path, capsys)
    assert code == 0, out
    orgs = json.loads(out)
    assert orgs["ok"] and orgs["organisms"]


def test_promote_code_cross_process(tmp_path: Path, capsys):
    """Bundle state must hydrate across separate CLI invocations."""
    code, out = _run(["evolve-code", "--intent", "Organism CLI scorer"], tmp_path, capsys)
    assert code == 0, out
    evolved = json.loads(out)
    bid = evolved["bundle"]["bundle_id"]
    assert evolved["bundle"]["gate"]["sandbox_ok"] is True
    assert evolved["bundle"]["gate"]["ready"] is True
    code, out = _run(["promote-code", "--bundle-id", bid], tmp_path, capsys)
    assert code == 0, out
    promoted = json.loads(out)
    assert promoted["ok"] and promoted["bundle"]["stage"] == "PROMOTED"
    assert "EXPLORATION" in promoted.get("product_limit", "")
    code, out = _run(["rollback-code"], tmp_path, capsys)
    assert code == 0, out
    assert json.loads(out)["bundle"]["stage"] == "ROLLBACK"


def test_bundle_roundtrip_cli(tmp_path: Path, capsys):
    root = tmp_path / "data"
    code, out = _run(["evolve-looks", "--brief", "bundle look", "--pack"], root, capsys)
    assert code == 0, out
    dest = tmp_path / "b.zip"
    code, out = _run(["bundle-export", "--path", str(dest)], root, capsys)
    assert code == 0, out
    exported = json.loads(out)
    assert exported["ok"]
    path = exported["result"]["path"]
    assert Path(path).is_file()
    code, out = _run(["bundle-import", "--path", path], root, capsys)
    assert code == 0, out
    assert json.loads(out)["ok"]
