"""v1.12 W7 and W9, the operator's label and adopt actions: the Python API and the CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from organism_sdk.cli import main
from organism_sdk.signing import TrustStore, generate_seed, public_key_for, sign
from organism_sdk.work import codec, operator
from organism_sdk.work.domain import Decision, Outcome, Verdict, decision_key
from organism_sdk.work.governance import PolicyRejected, policy_payload
from organism_sdk.work.policy import Policy
from organism_sdk.work.store import WorkStore


def saved_decision(store: WorkStore, trigger_id: str, pol: Policy) -> Decision:
    decided = Decision(
        id=decision_key(trigger_id, pol.version),
        trigger_id=trigger_id,
        outcome=Outcome.IGNORE,
        reasons=("cell_inferred", "would_accept"),
    )
    store.save_decision(decided)
    return decided


def write_policy(
    directory: Path, pol: Policy, *, signer: bytes, trusted: bytes
) -> tuple[Path, Path, Path]:
    policy_file = directory / "policy.json"
    signature_file = directory / "policy.sig"
    trust_file = directory / "trust.json"
    policy_file.write_text(codec.to_text(pol), encoding="utf-8")
    signature_file.write_text(sign(signer, policy_payload(pol.version)).hex(), encoding="utf-8")
    trust_file.write_text(
        json.dumps({"authors": [], "approvers": [public_key_for(trusted).hex()]}),
        encoding="utf-8",
    )
    return policy_file, signature_file, trust_file


def test_the_latest_verdict_on_a_decision_stands(tmp_path: Path) -> None:
    pol = Policy()
    with WorkStore(tmp_path / "work.sqlite") as store:
        decided = saved_decision(store, "m1", pol)
        operator.label(store, decided.id, Verdict.AGREE)
        operator.label(store, decided.id, Verdict.DISAGREE)
        assert store.labels() == {decided.id: Verdict.DISAGREE}


def test_a_verdict_on_an_unknown_decision_is_refused(tmp_path: Path) -> None:
    with WorkStore(tmp_path / "work.sqlite") as store, pytest.raises(KeyError):
        operator.label(store, "nope@sha256:0", Verdict.AGREE)


def test_the_cli_records_a_verdict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "work.sqlite"
    with WorkStore(path) as store:
        decided = saved_decision(store, "m2", Policy())
    assert main(["work", "label", decided.id, "agree", "--store", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "agree"
    with WorkStore(path, read_only=True) as store:
        assert store.labels() == {decided.id: Verdict.AGREE}


def test_the_cli_refuses_a_verdict_on_an_unknown_decision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "work.sqlite"
    WorkStore(path).close()
    assert main(["work", "label", "nope@sha256:0", "agree", "--store", str(path)]) == 1
    assert "no decision nope@sha256:0" in capsys.readouterr().out


def test_an_approver_signed_policy_takes_effect(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    approver = generate_seed()
    pol = Policy()
    policy_file, signature_file, trust_file = write_policy(
        tmp_path, pol, signer=approver, trusted=approver
    )
    path = tmp_path / "work.sqlite"
    args = [
        "work",
        "adopt",
        str(policy_file),
        "--signature",
        str(signature_file),
        "--trust",
        str(trust_file),
        "--store",
        str(path),
    ]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["policy"] == pol.version
    with WorkStore(path, read_only=True) as store:
        active = store.active_policy()
    assert active is not None
    assert active.version == pol.version


def test_a_policy_signed_by_an_author_key_does_not_take_effect(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    author = generate_seed()
    policy_file, signature_file, _ = write_policy(tmp_path, Policy(), signer=author, trusted=author)
    trust_file = tmp_path / "authors-only.json"
    trust_file.write_text(
        json.dumps({"authors": [public_key_for(author).hex()], "approvers": []}), encoding="utf-8"
    )
    path = tmp_path / "work.sqlite"
    args = [
        "work",
        "adopt",
        str(policy_file),
        "--signature",
        str(signature_file),
        "--trust",
        str(trust_file),
        "--store",
        str(path),
    ]
    assert main(args) == 1
    assert "not signed by an approver" in capsys.readouterr().out
    with WorkStore(path, read_only=True) as store:
        assert store.active_policy() is None


def test_a_signature_from_another_key_is_rejected_by_the_api(tmp_path: Path) -> None:
    approver = generate_seed()
    stranger = generate_seed()
    pol = Policy()
    with WorkStore(tmp_path / "work.sqlite") as store:
        with pytest.raises(PolicyRejected):
            operator.adopt(
                store,
                pol,
                signature=sign(stranger, policy_payload(pol.version)),
                trust=_trust_for(approver),
            )
        assert store.active_policy() is None


def _trust_for(approver: bytes) -> TrustStore:
    return TrustStore(authors=frozenset(), approvers=frozenset({public_key_for(approver)}))
