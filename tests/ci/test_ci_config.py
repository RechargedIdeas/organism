"""Pipeline configuration: validation of gates.yaml and pipeline.toml, command parsing, tiers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from organism_ci.config import (
    TIER_RANK,
    ConfigError,
    Gate,
    load_gates,
    load_pipeline,
    split_command,
)
from organism_ci.orchestrator import select_gates

ROOT = Path(__file__).resolve().parents[2]


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "gates.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_repo_gates_file_is_valid_and_ids_are_unique():
    gates = load_gates(ROOT / "ci" / "gates.yaml")
    ids = [g.id for g in gates]
    assert len(ids) == len(set(ids))
    assert {g.tier for g in gates} <= set(TIER_RANK)


def test_repo_gates_use_the_placeholder_not_a_hard_coded_venv_path():
    # A Linux-only venv path made every gate fail on Windows. Commands must use {python}.
    for gate in load_gates(ROOT / "ci" / "gates.yaml"):
        text = " ".join([gate.command or "", *gate.env.values()])
        assert ".venv/bin/python" not in text, gate.id
        assert ".venv/Scripts" not in text, gate.id


def test_repo_pipeline_settings_load():
    pipeline = load_pipeline(ROOT / "ci" / "pipeline.toml")
    assert pipeline.jobs >= 1
    assert pipeline.preflight.min_python == (3, 11)
    assert "sdk" in pipeline.inputs
    assert pipeline.env["QT_QPA_PLATFORM"] == "offscreen"


def test_builtin_and_command_are_mutually_exclusive(tmp_path):
    path = _write(tmp_path, "gates:\n  - id: a:b\n    command: echo\n    builtin: proto\n")
    with pytest.raises(ConfigError, match="exactly one"):
        load_gates(path)


def test_gate_needs_a_command_or_builtin(tmp_path):
    path = _write(tmp_path, "gates:\n  - id: a:b\n")
    with pytest.raises(ConfigError, match="exactly one"):
        load_gates(path)


def test_unknown_key_is_rejected_so_typos_cannot_pass_silently(tmp_path):
    path = _write(tmp_path, "gates:\n  - id: a:b\n    command: echo\n    blockign: false\n")
    with pytest.raises(ConfigError, match="unknown keys: blockign"):
        load_gates(path)


def test_duplicate_ids_are_rejected(tmp_path):
    path = _write(tmp_path, "gates:\n  - id: a:b\n    command: echo\n  - id: a:b\n    command: echo\n")
    with pytest.raises(ConfigError, match="duplicate"):
        load_gates(path)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("    tier: nightlyish\n    command: echo\n", "tier must be one of"),
        ("    retries: 9\n    command: echo\n", "retries must be"),
        ("    timeout_s: -1\n    command: echo\n", "timeout_s must be a positive number"),
        ("    requires: [docker]\n    command: echo\n", "unknown requires docker"),
        ("    blocking: maybe\n    command: echo\n", "blocking must be true or false"),
        ("    builtin: nope\n", "unknown builtin"),
    ],
)
def test_field_validation(tmp_path, body, message):
    path = _write(tmp_path, "gates:\n  - id: a:b\n" + body)
    with pytest.raises(ConfigError, match=message):
        load_gates(path)


def test_invalid_gate_id_is_rejected(tmp_path):
    path = _write(tmp_path, "gates:\n  - id: Bad Id\n    command: echo\n")
    with pytest.raises(ConfigError, match="invalid gate id"):
        load_gates(path)


def test_documentation_sections_are_ignored(tmp_path):
    path = _write(
        tmp_path,
        "gates:\n  - id: a:b\n    command: echo\ncategory_bio:\n  - id: J1\n    status: green\n",
    )
    assert [g.id for g in load_gates(path)] == ["a:b"]


def test_split_command_separates_env_and_fills_placeholders_after_splitting():
    windows_python = r"H:\Projects\Organism\.venv\Scripts\python.exe"
    command = split_command(
        "PYTHONPATH=sdk/python:modules:. QT_QPA_PLATFORM=offscreen {python} -m pytest -q -m 'not slow'",
        {"python": windows_python},
    )
    assert command.argv == (windows_python, "-m", "pytest", "-q", "-m", "not slow")
    assert command.env["QT_QPA_PLATFORM"] == "offscreen"
    assert command.env["PYTHONPATH"] == os.pathsep.join(["sdk/python", "modules", "."])


def test_split_command_rejects_empty_program():
    with pytest.raises(ConfigError, match="no program"):
        split_command("FOO=bar", {})


def test_split_command_reports_unbalanced_quotes():
    with pytest.raises(ConfigError, match="cannot parse"):
        split_command("{python} -c 'unclosed", {"python": "py"})


def _gate(gate_id: str, tier: str, *, builtin: str | None = None) -> Gate:
    return Gate(
        id=gate_id,
        tier=tier,
        command=None if builtin else "echo",
        builtin=builtin,
        env={},
        blocking=True,
        exclusive=False,
        cacheable=True,
        retries=0,
        timeout_s=None,
        requires=(),
        inputs=(),
    )


def test_tier_selection_runs_a_gate_in_its_tier_and_above():
    gates = [_gate("p", "precommit"), _gate("f", "fast"), _gate("u", "full"), _gate("n", "nightly")]
    selected = {tier: [g.id for g in select_gates(gates, tier, ())] for tier in TIER_RANK}
    assert selected == {
        "precommit": ["p"],
        "fast": ["p", "f"],
        "full": ["p", "f", "u"],
        "nightly": ["p", "f", "u", "n"],
    }


def test_only_selects_by_id_across_tiers_and_rejects_unknown_ids():
    gates = [_gate("p", "precommit"), _gate("n", "nightly")]
    assert [g.id for g in select_gates(gates, "fast", ("n",))] == ["n"]
    with pytest.raises(ConfigError, match="unknown gate id"):
        select_gates(gates, "fast", ("missing",))
