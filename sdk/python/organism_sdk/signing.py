"""Ed25519 signatures for registry registration and promotion.

A signature binds one registry action to one key. Every payload starts with a domain tag, so a
signature made for a registration cannot be replayed as a promotion, or the other way round.

``cryptography`` is imported only when a signature is made or checked. Code that never signs or
verifies does not need it installed.
"""
from __future__ import annotations

import json
import secrets
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from organism_sdk.registry import ShadowValidationRecord

PUBLIC_KEY_BYTES = 32
PRIVATE_SEED_BYTES = 32
SIGNATURE_BYTES = 64

_REGISTER_DOMAIN = b"organism.registry.register.v1\n"
_PROMOTE_DOMAIN = b"organism.registry.promote.v1\n"


def registration_payload(module_id: str, version: str, artifact_digest: bytes) -> bytes:
    """Bytes an author signs to register one module version with one artifact."""
    body = {"module_id": module_id, "version": version, "artifact_digest": artifact_digest.hex()}
    return _REGISTER_DOMAIN + _canonical(body)


def promotion_payload(
    module_id: str,
    from_state: str,
    to_state: str,
    shadow_records: Sequence[ShadowValidationRecord],
) -> bytes:
    """Bytes an approver signs to move a module from one lifecycle state to another.

    The shadow evidence is part of the payload, so an approval cannot be reused with different
    evidence.
    """
    body = {
        "module_id": module_id,
        "from_state": from_state,
        "to_state": to_state,
        "shadow": [_shadow_json(r) for r in shadow_records],
    }
    return _PROMOTE_DOMAIN + _canonical(body)


def _shadow_json(record: ShadowValidationRecord) -> dict[str, Any]:
    return {
        "invocations": record.invocations,
        "incumbent_error": record.incumbent_error,
        "candidate_error": record.candidate_error,
        "p95_latency_ms": record.p95_latency_ms,
        "gates_passed": list(record.gates_passed),
        "evidence_digest": record.evidence_digest.hex(),
    }


def _canonical(body: dict[str, Any]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class TrustStore:
    """Public keys that may authorize registrations (``authors``) and promotions (``approvers``).

    A key listed as an author cannot approve a promotion, and an approver cannot register a
    module. An empty store trusts nothing, so the registry rejects every signed action.
    """

    authors: frozenset[bytes] = frozenset()
    approvers: frozenset[bytes] = frozenset()

    def __post_init__(self) -> None:
        for key in self.authors | self.approvers:
            if len(key) != PUBLIC_KEY_BYTES:
                raise ValueError(f"public key must be {PUBLIC_KEY_BYTES} bytes, got {len(key)}")


def load_trust_store(path: Path) -> TrustStore:
    """Read a trust store file: ``{"authors": ["<hex>", ...], "approvers": ["<hex>", ...]}``."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return TrustStore(
        authors=frozenset(bytes.fromhex(k) for k in data.get("authors", [])),
        approvers=frozenset(bytes.fromhex(k) for k in data.get("approvers", [])),
    )


def generate_seed() -> bytes:
    """Return a new 32-byte Ed25519 private seed. Keep it secret."""
    return secrets.token_bytes(PRIVATE_SEED_BYTES)


def public_key_for(seed: bytes) -> bytes:
    """Return the raw 32-byte public key for a private seed."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    public = Ed25519PrivateKey.from_private_bytes(seed).public_key()
    return public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def sign(seed: bytes, payload: bytes) -> bytes:
    """Sign ``payload`` with a private seed and return the 64-byte signature."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    return Ed25519PrivateKey.from_private_bytes(seed).sign(payload)


def verify(public_key: bytes, signature: bytes, payload: bytes) -> bool:
    """Return True when ``signature`` is a valid Ed25519 signature of ``payload``.

    Malformed keys and signatures return False. They never raise.
    """
    if len(public_key) != PUBLIC_KEY_BYTES or len(signature) != SIGNATURE_BYTES:
        return False
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, payload)
    except (InvalidSignature, ValueError):
        return False
    return True


def verify_any(public_keys: Iterable[bytes], signature: bytes, payload: bytes) -> bool:
    """Return True when any of the keys verifies ``signature`` over ``payload``."""
    return any(verify(key, signature, payload) for key in public_keys)
