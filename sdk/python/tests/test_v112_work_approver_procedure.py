"""v1.12 W9, the approver's signing procedure: the offline script makes a key outside the repository
and signs a Policy's version, and the operator's `organism work adopt` accepts that signature and
refuses another. These tests use test keys only; the production approver key never enters the repo
(decision S1)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from organism_sdk import cli
from organism_sdk.work import codec
from organism_sdk.work.policy import AcceptMode, AdmissionRow, Policy, Rule, SourcePolicy
from organism_sdk.work.store import WorkStore

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "docs" / "v1.12" / "approver" / "approve_policy.py"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def policy() -> Policy:
    github = SourcePolicy(
        source="github", allowed=frozenset({"alice"}), rows={"repo": AdmissionRow()}
    )
    rule = Rule(id="ci-fix", instruction="fix CI", pattern="CI")
    return Policy(mode=AcceptMode.OBSERVE, rules=(rule,), sources=(github,))


def write_trust(path: Path, approver_seed: Path) -> None:
    approver = run_script("public", str(approver_seed)).stdout.strip()
    path.write_text(json.dumps({"authors": [], "approvers": [approver]}), encoding="utf-8")


def adopt_args(policy_file: Path, signature: Path, trust: Path, store: Path) -> list[str]:
    return [
        "work",
        "adopt",
        str(policy_file),
        "--signature",
        str(signature),
        "--trust",
        str(trust),
        "--store",
        str(store),
    ]


def test_keygen_writes_a_seed_outside_the_repo_and_prints_its_public_key(tmp_path: Path) -> None:
    seed = tmp_path / "approver-seed.hex"
    made = run_script("keygen", str(seed))
    assert made.returncode == 0, made.stderr
    assert len(bytes.fromhex(seed.read_text(encoding="utf-8").strip())) == 32
    assert len(bytes.fromhex(made.stdout.strip())) == 32
    assert run_script("public", str(seed)).stdout.strip() == made.stdout.strip()


def test_keygen_never_overwrites_a_seed(tmp_path: Path) -> None:
    seed = tmp_path / "approver-seed.hex"
    original = "00" * 32
    seed.write_text(original, encoding="utf-8")
    refused = run_script("keygen", str(seed))
    assert refused.returncode != 0
    assert "never overwritten" in refused.stderr
    assert seed.read_text(encoding="utf-8") == original


def test_a_seed_inside_the_repository_is_refused_before_anything_is_read_or_written() -> None:
    inside = REPO / "approver-seed-that-does-not-exist.hex"
    refused = run_script("public", str(inside))
    assert refused.returncode != 0
    assert "inside the repository" in refused.stderr
    made = run_script("keygen", str(inside))
    assert made.returncode != 0
    assert "inside the repository" in made.stderr
    assert not inside.exists()


def test_an_operator_adopts_a_policy_the_approver_signed_offline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed = tmp_path / "approver-seed.hex"
    assert run_script("keygen", str(seed)).returncode == 0
    trust = tmp_path / "trust.json"
    write_trust(trust, seed)
    pol = policy()
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(codec.to_text(pol), encoding="utf-8")
    signature = tmp_path / "signature.hex"
    signed = run_script("sign", str(policy_file), str(seed), str(signature))
    assert signed.returncode == 0, signed.stderr
    assert signed.stdout.strip() == pol.version
    store = tmp_path / "work.sqlite"
    assert cli.main(adopt_args(policy_file, signature, trust, store)) == 0
    assert json.loads(capsys.readouterr().out)["policy"] == pol.version
    with WorkStore(store) as handle:
        assert handle.active_policy() == pol


def test_a_policy_signed_with_another_key_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    approver = tmp_path / "approver-seed.hex"
    stranger = tmp_path / "stranger-seed.hex"
    assert run_script("keygen", str(approver)).returncode == 0
    assert run_script("keygen", str(stranger)).returncode == 0
    trust = tmp_path / "trust.json"
    write_trust(trust, approver)
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(codec.to_text(policy()), encoding="utf-8")
    signature = tmp_path / "signature.hex"
    assert run_script("sign", str(policy_file), str(stranger), str(signature)).returncode == 0
    store = tmp_path / "work.sqlite"
    assert cli.main(adopt_args(policy_file, signature, trust, store)) == 1
    assert "not signed by an approver" in json.loads(capsys.readouterr().out)["error"]
