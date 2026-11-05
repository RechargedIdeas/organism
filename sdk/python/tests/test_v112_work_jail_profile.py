"""v1.12 W5, the `work_executor` profile and the environment allowlist it uses."""

from __future__ import annotations

from organism_sdk.sandbox.jail import ENV_BASE, allowlisted_env
from organism_sdk.sandbox.policy import SandboxPolicy
from organism_sdk.work.executors import containment_gap


def test_the_profile_is_bounded_and_names_its_hosts() -> None:
    policy = SandboxPolicy.work_executor()
    assert policy.label == "work_executor"
    assert policy.timeout_s == 1800.0
    assert policy.allow_network is True
    assert "api.anthropic.com" in policy.network_allowlist
    assert "*" not in policy.network_allowlist
    assert policy.deny_shell_escape is True


def test_the_profile_passes_the_one_key_variable_by_name() -> None:
    assert SandboxPolicy.work_executor().env_allowlist == ("ANTHROPIC_API_KEY",)


def test_the_allowlist_keeps_the_base_and_the_named_variables_only() -> None:
    source = {
        "PATH": "/bin",
        "HOME": "/home/w",
        "ANTHROPIC_API_KEY": "test-key",
        "AWS_SECRET_ACCESS_KEY": "test-secret",
        "OTHER": "test-other",
    }
    env = allowlisted_env(("ANTHROPIC_API_KEY",), source=source)
    assert env == {"PATH": "/bin", "HOME": "/home/w", "ANTHROPIC_API_KEY": "test-key"}


def test_the_caller_can_add_variables_to_an_allowlisted_child() -> None:
    env = allowlisted_env((), source={"PATH": "/bin"}, extra={"ORGANISM_WORK_DIR": "/work"})
    assert env == {"PATH": "/bin", "ORGANISM_WORK_DIR": "/work"}


def test_only_the_base_is_kept_without_a_name() -> None:
    assert "PATH" in ENV_BASE
    assert "ANTHROPIC_API_KEY" not in ENV_BASE


def test_the_audit_form_records_the_allowlist() -> None:
    assert SandboxPolicy.work_executor().as_dict()["env_allowlist"] == ["ANTHROPIC_API_KEY"]
    assert SandboxPolicy.generative().as_dict()["env_allowlist"] is None


def test_containment_needs_linux_rlimits_and_namespaces() -> None:
    full = {"linux": True, "rlimits": True, "unshare": True}
    assert containment_gap(full) is None
    assert "Linux" in (containment_gap({**full, "linux": False}) or "")
    assert "rlimits" in (containment_gap({**full, "rlimits": False}) or "")
    assert "namespaces" in (containment_gap({**full, "unshare": False}) or "")
