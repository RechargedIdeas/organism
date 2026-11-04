"""Gate environments: values may use the same placeholders as commands."""

from __future__ import annotations

from pathlib import Path

from organism_ci.cache import key_environment
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


def test_cache_key_environment_ignores_session_noise_and_keeps_what_matters() -> None:
    # Before this, every session-specific variable changed the key, so a pre-push run and a
    # terminal run never shared a cache entry.
    terminal = {"PYTHONUTF8": "1", "PATH": "/usr/bin", "TERM_SESSION_ID": "a", "ORGANISM_SANDBOX_ISOLATE": "1"}
    # Git for Windows adds LC_CTYPE to hook environments; this difference used to split the cache.
    hook = {"PYTHONUTF8": "1", "PATH": "/hook/bin", "TERM_SESSION_ID": "b", "GIT_INDEX_FILE": "x",
            "LC_CTYPE": "C.UTF-8", "ORGANISM_SANDBOX_ISOLATE": "1"}
    declared = {"PYTHONUTF8"}
    assert key_environment(terminal, declared) == key_environment(hook, declared)
    assert key_environment(terminal, declared) == {"PYTHONUTF8": "1", "ORGANISM_SANDBOX_ISOLATE": "1"}
    changed = {**terminal, "ORGANISM_SANDBOX_ISOLATE": "0"}
    assert key_environment(changed, declared) != key_environment(terminal, declared)
    # A gate-declared name is keyed even without an outcome prefix.
    assert key_environment({"PATH": "/x", "MY_FLAG": "1"}, {"MY_FLAG"}) == {"MY_FLAG": "1"}
