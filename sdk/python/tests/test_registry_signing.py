"""Signed registration and promotion: the trust store decides which signatures count."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from deterministic_engine.engine import DeterministicEngine
from learned_module.module import LearnedModule
from organism_sdk import signing
from organism_sdk.contract import SubstrateContract
from organism_sdk.deploy.config import (
    default_cpu_only_config,
    load_deploy_config,
    validate_deploy_config,
)
from organism_sdk.deploy.stack import BUILTIN_MODULE_IDS, build_minimal_stack
from organism_sdk.errors import RegistrationRejected
from organism_sdk.registry import RegistryClient, ShadowValidationRecord
from organism_sdk.signing import TrustStore, load_trust_store

Keypair = tuple[bytes, bytes]

SHADOW = [
    ShadowValidationRecord(
        invocations=100,
        incumbent_error=0.1,
        candidate_error=0.09,
        p95_latency_ms=2.0,
        gates_passed=("sandbox",),
    )
]
WEAKER = [
    ShadowValidationRecord(
        invocations=1,
        incumbent_error=0.1,
        candidate_error=0.5,
        p95_latency_ms=2.0,
    )
]


def _keypair() -> Keypair:
    seed = signing.generate_seed()
    return seed, signing.public_key_for(seed)


@pytest.fixture
def author() -> Keypair:
    return _keypair()


@pytest.fixture
def approver() -> Keypair:
    return _keypair()


def _contract() -> SubstrateContract:
    return DeterministicEngine().declare_contract()


def _sign_registration(seed: bytes, contract: SubstrateContract, artifact_digest: bytes) -> bytes:
    payload = signing.registration_payload(
        contract.identity.module_id, contract.identity.version, artifact_digest
    )
    return signing.sign(seed, payload)


def _sign_promotion(seed: bytes, module_id: str, records: list[ShadowValidationRecord]) -> bytes:
    payload = signing.promotion_payload(module_id, "PROPOSED", "SANDBOXED", records)
    return signing.sign(seed, payload)


def _registry(
    *, authors: frozenset[bytes] = frozenset(), approvers: frozenset[bytes] = frozenset()
) -> RegistryClient:
    return RegistryClient(trust_store=TrustStore(authors=authors, approvers=approvers))


def _register_signed(reg: RegistryClient, seed: bytes) -> str:
    c = _contract()
    digest = c.identity.artifact_digest
    reg.register(
        c,
        artifact_digest=digest,
        author_signature=_sign_registration(seed, c, digest),
    )
    return c.identity.module_id


def test_sign_verify_roundtrip() -> None:
    seed, public = _keypair()
    sig = signing.sign(seed, b"message")
    assert len(sig) == signing.SIGNATURE_BYTES
    assert signing.verify(public, sig, b"message")
    assert not signing.verify(public, sig, b"other message")
    assert not signing.verify(public, sig[:-1], b"message")
    assert not signing.verify(public[:-1], sig, b"message")
    assert not signing.verify(_keypair()[1], sig, b"message")


def test_payloads_are_domain_separated() -> None:
    c = _contract()
    register = signing.registration_payload(
        c.identity.module_id, c.identity.version, c.identity.artifact_digest
    )
    promote = signing.promotion_payload(c.identity.module_id, "PROPOSED", "SANDBOXED", SHADOW)
    assert register != promote
    seed, public = _keypair()
    assert not signing.verify(public, signing.sign(seed, register), promote)


def test_registration_payload_binds_version_and_artifact() -> None:
    c = _contract()
    mid, digest = c.identity.module_id, c.identity.artifact_digest
    base = signing.registration_payload(mid, "1.0.0", digest)
    assert base != signing.registration_payload(mid, "1.0.1", digest)
    assert base != signing.registration_payload(mid, "1.0.0", bytes(32))


def test_promotion_payload_binds_target_state_and_evidence() -> None:
    mid = _contract().identity.module_id
    base = signing.promotion_payload(mid, "PROPOSED", "SANDBOXED", SHADOW)
    assert base != signing.promotion_payload(mid, "PROPOSED", "SHADOW_VALIDATED", SHADOW)
    assert base != signing.promotion_payload(mid, "PROPOSED", "SANDBOXED", WEAKER)


def test_registry_without_trust_store_does_not_check_signatures() -> None:
    c = _contract()
    reg = RegistryClient()
    resp = reg.register(c, artifact_digest=c.identity.artifact_digest, author_signature=b"deploy")
    assert resp.initial_state == "PROPOSED"


def test_trusted_author_can_register(author: Keypair) -> None:
    seed, public = author
    reg = _registry(authors=frozenset({public}))
    module_id = _register_signed(reg, seed)
    assert reg.list_module_ids() == [module_id]


def test_untrusted_signer_cannot_register(author: Keypair) -> None:
    _, public = author
    stranger_seed, _ = _keypair()
    c = _contract()
    reg = _registry(authors=frozenset({public}))
    with pytest.raises(RegistrationRejected) as exc:
        reg.register(
            c,
            artifact_digest=c.identity.artifact_digest,
            author_signature=_sign_registration(stranger_seed, c, c.identity.artifact_digest),
        )
    assert [i.code for i in exc.value.issues] == ["signature_invalid"]
    assert reg.list_module_ids() == []


def test_signature_for_one_artifact_does_not_register_another(author: Keypair) -> None:
    seed, public = author
    c = _contract()
    reg = _registry(authors=frozenset({public}))
    with pytest.raises(RegistrationRejected):
        reg.register(
            c,
            artifact_digest=bytes(32),
            author_signature=_sign_registration(seed, c, c.identity.artifact_digest),
        )


def test_approver_key_cannot_register(approver: Keypair) -> None:
    seed, public = approver
    c = _contract()
    reg = _registry(approvers=frozenset({public}))
    with pytest.raises(RegistrationRejected):
        reg.register(
            c,
            artifact_digest=c.identity.artifact_digest,
            author_signature=_sign_registration(seed, c, c.identity.artifact_digest),
        )


def test_empty_trust_store_rejects_every_registration(author: Keypair) -> None:
    seed, _ = author
    c = _contract()
    reg = _registry()
    with pytest.raises(RegistrationRejected):
        reg.register(
            c,
            artifact_digest=c.identity.artifact_digest,
            author_signature=_sign_registration(seed, c, c.identity.artifact_digest),
        )


def test_trusted_approver_can_promote(author: Keypair, approver: Keypair) -> None:
    author_seed, author_public = author
    approver_seed, approver_public = approver
    reg = _registry(authors=frozenset({author_public}), approvers=frozenset({approver_public}))
    module_id = _register_signed(reg, author_seed)
    sig = _sign_promotion(approver_seed, module_id, SHADOW)
    result = reg.promote(module_id, "PROPOSED", "SANDBOXED", SHADOW, sig)
    assert result.accepted, result.validation_issues


def test_untrusted_approver_cannot_promote(author: Keypair) -> None:
    author_seed, author_public = author
    reg = _registry(authors=frozenset({author_public}))
    module_id = _register_signed(reg, author_seed)
    stranger_seed, _ = _keypair()
    sig = _sign_promotion(stranger_seed, module_id, SHADOW)
    result = reg.promote(module_id, "PROPOSED", "SANDBOXED", SHADOW, sig)
    assert not result.accepted
    assert [i.code for i in result.validation_issues] == ["signature_invalid"]


def test_author_key_cannot_approve(author: Keypair) -> None:
    seed, public = author
    reg = _registry(authors=frozenset({public}))
    module_id = _register_signed(reg, seed)
    sig = _sign_promotion(seed, module_id, SHADOW)
    assert not reg.promote(module_id, "PROPOSED", "SANDBOXED", SHADOW, sig).accepted


def test_approval_cannot_be_reused_with_different_evidence(
    author: Keypair, approver: Keypair
) -> None:
    author_seed, author_public = author
    approver_seed, approver_public = approver
    reg = _registry(authors=frozenset({author_public}), approvers=frozenset({approver_public}))
    module_id = _register_signed(reg, author_seed)
    sig = _sign_promotion(approver_seed, module_id, SHADOW)
    assert not reg.promote(module_id, "PROPOSED", "SANDBOXED", WEAKER, sig).accepted


def test_load_trust_store_reads_hex_keys(tmp_path: Path, author: Keypair) -> None:
    _, public = author
    path = tmp_path / "trust.json"
    path.write_text(json.dumps({"authors": [public.hex()], "approvers": []}), encoding="utf-8")
    store = load_trust_store(path)
    assert store.authors == frozenset({public})
    assert store.approvers == frozenset()


def test_trust_store_rejects_keys_of_the_wrong_length() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        TrustStore(authors=frozenset({b"short"}))


def test_a_built_in_module_registers_without_an_author_signature() -> None:
    contract = _contract()
    module_id = contract.identity.module_id
    reg = RegistryClient(trust_store=TrustStore(), builtin_ids=frozenset({module_id}))
    reg.register(
        contract,
        artifact_digest=contract.identity.artifact_digest,
        author_signature=b"deploy",
    )
    assert module_id in reg.list_module_ids()


def test_a_module_not_on_the_built_in_list_still_needs_an_author_signature() -> None:
    contract = _contract()
    reg = RegistryClient(trust_store=TrustStore(), builtin_ids=frozenset({"someone_else"}))
    with pytest.raises(RegistrationRejected):
        reg.register(
            contract,
            artifact_digest=contract.identity.artifact_digest,
            author_signature=b"deploy",
        )
    assert contract.identity.module_id not in reg.list_module_ids()


def test_the_built_in_ids_are_the_two_modules_the_stack_registers() -> None:
    declared = {
        _contract().identity.module_id,
        LearnedModule(precalibrate=False).declare_contract().identity.module_id,
    }
    assert declared == BUILTIN_MODULE_IDS


def test_a_stack_with_a_trust_store_registers_its_built_in_modules(
    tmp_path: Path, author: Keypair
) -> None:
    _, public = author
    trust = tmp_path / "trust.json"
    trust.write_text(json.dumps({"authors": [public.hex()], "approvers": []}), encoding="utf-8")
    cfg = default_cpu_only_config()
    cfg.stack.trust_store = str(trust)
    stack = build_minimal_stack(cfg)
    assert set(stack.modules) == BUILTIN_MODULE_IDS
    assert BUILTIN_MODULE_IDS <= set(stack.registry.list_module_ids())


def test_a_trust_store_path_is_read_from_the_deploy_config(tmp_path: Path) -> None:
    trust = str(tmp_path / "trust.json")
    path = tmp_path / "deploy.json"
    path.write_text(json.dumps({"stack": {"trust_store": trust}}), encoding="utf-8")
    cfg = load_deploy_config(path)
    assert cfg.stack.trust_store == trust
    assert cfg.as_dict()["stack"]["trust_store"] == trust


def test_a_missing_or_malformed_trust_store_is_reported_by_validation(tmp_path: Path) -> None:
    cfg = default_cpu_only_config()
    cfg.stack.trust_store = str(tmp_path / "missing.json")
    assert any(i.startswith("stack.trust_store:") for i in validate_deploy_config(cfg))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"approvers": ["not-hex"]}), encoding="utf-8")
    cfg.stack.trust_store = str(bad)
    assert any(i.startswith("stack.trust_store:") for i in validate_deploy_config(cfg))
