"""v1.12 environment store: a secret value stays out of reprs, errors, logs, status output and children.

The sentinel below is a fake value. Every test looks for it in the text a leak would travel through.
"""

from __future__ import annotations

import json
import logging
import pickle
import sys
import uuid
from pathlib import Path

import pytest
from organism_sdk import envstore
from organism_sdk.cli import main as cli_main
from organism_sdk.deploy.config import default_cpu_only_config
from organism_sdk.deploy.stack import build_minimal_stack
from organism_sdk.envstore import (
    MASK,
    EnvStore,
    EnvStoreError,
    FileBackend,
    Secret,
    apply_to_environ,
    check_name,
    check_value,
    default_backend,
    default_file_path,
    without_stored,
)
from organism_sdk.sandbox.jail import ProcessJail
from organism_sdk.sandbox.policy import SandboxPolicy

SENTINEL = "sentinel-7f3a91c0-not-a-secret"


@pytest.fixture(autouse=True)
def no_stored_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(envstore, "_stored_names", frozenset())


def reveal_of(store: EnvStore, name: str) -> str:
    secret = store.get(name)
    assert secret is not None, name
    return secret.reveal()


def test_a_secret_shows_a_mask_and_reveals_only_on_request() -> None:
    secret = Secret(SENTINEL)
    assert secret.reveal() == SENTINEL
    for shown in (repr(secret), str(secret), f"{secret}", f"{secret:>40}", repr([secret])):
        assert SENTINEL not in shown
    assert str(secret) == MASK


def test_a_secret_does_not_pickle() -> None:
    with pytest.raises(TypeError) as error:
        pickle.dumps(Secret(SENTINEL))
    assert SENTINEL not in str(error.value)


def test_names_are_checked_and_never_echoed() -> None:
    for bad in ("lower_case", "1LEADING", "HAS SPACE", "", f"{SENTINEL.upper()}=x"):
        with pytest.raises(EnvStoreError) as error:
            check_name(bad)
        assert SENTINEL.upper() not in str(error.value)
    assert check_name("ORGANISM_LLM_API_KEY") == "ORGANISM_LLM_API_KEY"


def test_values_are_checked_and_never_echoed() -> None:
    with pytest.raises(EnvStoreError, match="empty"):
        check_value("")
    with pytest.raises(EnvStoreError) as nul:
        check_value(SENTINEL + "\x00")
    assert SENTINEL not in str(nul.value)
    with pytest.raises(EnvStoreError, match="larger than 2048 bytes"):
        check_value("x" * 2049)
    assert check_value("x" * 2048) == "x" * 2048
    with pytest.raises(EnvStoreError) as lone:
        check_value(SENTINEL + "\ud800")
    assert SENTINEL not in str(lone.value)
    assert lone.value.__cause__ is None


def test_a_file_store_round_trips(tmp_path: Path) -> None:
    store = EnvStore(FileBackend(tmp_path / "organism" / "env.json"))
    store.put("ORGANISM_LLM_API_KEY", SENTINEL)
    store.put("OTHER_TOKEN", "other-value")
    assert store.names() == ["ORGANISM_LLM_API_KEY", "OTHER_TOKEN"]
    assert reveal_of(store, "ORGANISM_LLM_API_KEY") == SENTINEL
    assert store.get("MISSING_NAME") is None
    store.put("OTHER_TOKEN", "replaced")
    assert reveal_of(store, "OTHER_TOKEN") == "replaced"
    assert store.remove("OTHER_TOKEN") is True
    assert store.remove("OTHER_TOKEN") is False
    assert store.names() == ["ORGANISM_LLM_API_KEY"]


def test_the_file_holds_the_variables_and_no_temporary_files(tmp_path: Path) -> None:
    EnvStore(FileBackend(tmp_path / "env.json")).put("A_KEY", SENTINEL)
    document = json.loads((tmp_path / "env.json").read_text(encoding="utf-8"))
    assert document == {"format": 1, "variables": {"A_KEY": SENTINEL}}
    assert not list(tmp_path.glob(".env-*.tmp"))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_the_file_and_its_directory_are_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "organism" / "env.json"
    EnvStore(FileBackend(path)).put("A_KEY", SENTINEL)
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    path.chmod(0o644)
    assert reveal_of(EnvStore(FileBackend(path)), "A_KEY") == SENTINEL
    assert path.stat().st_mode & 0o777 == 0o600


def test_a_damaged_file_names_no_value(tmp_path: Path) -> None:
    path = tmp_path / "env.json"
    path.write_text('{"format": 1, "variables": {"A_KEY": "' + SENTINEL, encoding="utf-8")
    with pytest.raises(EnvStoreError) as error:
        EnvStore(FileBackend(path)).get("A_KEY")
    assert SENTINEL not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__


def test_the_default_backend_is_the_platform_store() -> None:
    backend = default_backend()
    if sys.platform == "win32":
        assert type(backend).__name__ == "CredentialManager"
    else:
        assert isinstance(backend, FileBackend)
        assert backend.path == default_file_path()


def test_the_default_file_is_outside_the_repository() -> None:
    repo_root = Path(envstore.__file__).resolve().parents[3]
    assert repo_root not in default_file_path().resolve().parents


def test_apply_sets_only_what_the_environment_does_not(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = EnvStore(FileBackend(tmp_path / "env.json"))
    store.put("STORED_A", SENTINEL)
    store.put("STORED_B", "stored-b-value")
    environ = {"STORED_B": "explicit-b"}
    with caplog.at_level(logging.INFO, logger="organism_sdk.envstore"):
        applied = apply_to_environ(store=store, environ=environ)
    assert applied == ["STORED_A"]
    assert environ == {"STORED_A": SENTINEL, "STORED_B": "explicit-b"}
    assert "STORED_A" in caplog.text
    assert SENTINEL not in caplog.text


def test_a_child_does_not_inherit_a_stored_name(tmp_path: Path) -> None:
    store = EnvStore(FileBackend(tmp_path / "env.json"))
    store.put("STORED_A", SENTINEL)
    apply_to_environ(store=store, environ={})
    assert without_stored({"STORED_A": SENTINEL, "PATH": "/bin"}) == {"PATH": "/bin"}


def test_a_sandboxed_child_does_not_receive_a_stored_value(tmp_path: Path) -> None:
    store = EnvStore(FileBackend(tmp_path / "env.json"))
    store.put("STORED_A", SENTINEL)
    apply_to_environ(store=store, environ={})
    code = "import os; print('present' if 'STORED_A' in os.environ else 'absent')"
    result = ProcessJail(SandboxPolicy(use_namespaces=False)).run(
        [sys.executable, "-c", code], env={"STORED_A": SENTINEL}
    )
    assert result.ok, result
    assert result.stdout.strip() == "absent"
    assert SENTINEL not in result.stdout + result.stderr


def test_an_unreadable_store_starts_the_process_without_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "env.json"
    path.write_text('{"format": 1, "variables": {"A_KEY": "' + SENTINEL + '"', encoding="utf-8")
    environ: dict[str, str] = {}
    with caplog.at_level(logging.WARNING, logger="organism_sdk.envstore"):
        assert apply_to_environ(store=EnvStore(FileBackend(path)), environ=environ) == []
    assert environ == {}
    assert "not applied" in caplog.text
    assert SENTINEL not in caplog.text


def test_the_status_and_health_payloads_carry_no_stored_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORGANISM_LLM_API_KEY", SENTINEL)
    stack = build_minimal_stack(default_cpu_only_config())
    assert SENTINEL not in json.dumps(stack.status(), default=str)
    health = stack.health_report().to_json()
    assert SENTINEL not in (health if isinstance(health, str) else health.decode("utf-8"))


def test_cli_output_carries_no_stored_value(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ORGANISM_LLM_API_KEY", SENTINEL)
    cli_main(["status"])
    captured = capsys.readouterr()
    assert SENTINEL not in captured.out + captured.err


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Credential Manager")
def test_windows_credential_manager_round_trips() -> None:
    from organism_sdk.envstore_windows import CredentialManager

    store = EnvStore(CredentialManager(f"organism:envtest-{uuid.uuid4().hex}:"))
    try:
        store.put("STORE_TEST_A", SENTINEL)
        store.put("STORE_TEST_B", "ünïcode-value")
        assert store.names() == ["STORE_TEST_A", "STORE_TEST_B"]
        assert reveal_of(store, "STORE_TEST_A") == SENTINEL
        assert reveal_of(store, "STORE_TEST_B") == "ünïcode-value"
        assert store.get("STORE_TEST_C") is None
        assert store.remove("STORE_TEST_A") is True
        assert store.remove("STORE_TEST_A") is False
        assert store.names() == ["STORE_TEST_B"]
    finally:
        for name in store.names():
            store.remove(name)
