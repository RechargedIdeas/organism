"""JustificationToken + VerificationResult — A3.1 + R-13 / Amendment 3.1.3."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from organism_sdk.contract import JustificationKind
from organism_sdk.errors import JustificationMissing  # re-export


@dataclass(frozen=True)
class VerificationResult:
    """Bound to A1.6 VERIFIED | REJECTED(reason_code)."""

    outcome: Literal["VERIFIED", "REJECTED"]
    reason_code: str | None
    reason_params: dict[str, str]
    verifier_id: str
    verifier_contract_digest: bytes
    verified_at: datetime


class VerifierRole(Protocol):
    """Minimal verifier surface used by JustificationToken.verify."""

    def verifier_id(self) -> str: ...
    def contract_digest(self) -> bytes: ...
    def verify_token(self, token: "JustificationToken") -> VerificationResult: ...


@dataclass(frozen=True)
class JustificationToken:
    kind: JustificationKind
    format: str
    body: bytes
    signature: bytes

    def verify(self, verifier: VerifierRole) -> VerificationResult:
        return verifier.verify_token(self)


@dataclass(frozen=True)
class Emission:
    """Module emission envelope used by the SDK handle path."""

    action_class: str
    payload: bytes
    metadata: dict[str, str] = field(default_factory=dict)
    justification: JustificationToken | None = None
