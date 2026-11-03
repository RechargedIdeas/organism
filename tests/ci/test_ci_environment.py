"""Gate environments: values may use the same placeholders as commands."""

from __future__ import annotations

from pathlib import Path

from organism_ci.environment import Tools, build_env


def test_gate_env_placeholder_resolves_to_the_tool_path(tmp_path: Path) -> None:
    # Regression: a literal "{protoc}" reached build.rs, so prost could not find protoc.
    tools = Tools(root=tmp_path, protoc=tmp_path / "protoc.exe")
    env = build_env(tools, {}, {"PROTOC": "{protoc}"})
    assert env["PROTOC"] == tools.placeholders()["protoc"]
    assert "{protoc}" not in env["PROTOC"]


def test_gate_env_without_placeholders_is_unchanged(tmp_path: Path) -> None:
    tools = Tools(root=tmp_path)
    assert build_env(tools, {}, {"ORGANISM_SOAK_FULL": "1"})["ORGANISM_SOAK_FULL"] == "1"
