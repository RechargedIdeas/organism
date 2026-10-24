"""OrganismModule ABC + SDK handle path (SDK-4: justify inside SDK)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

from organism_sdk.contract import JustificationKind, SubstrateContract
from organism_sdk.errors import JustificationMissing
from organism_sdk.health import HealthReport
from organism_sdk.inputs import PerceptionInput
from organism_sdk.justification import Emission, JustificationToken

if TYPE_CHECKING:
    pass


class OrganismModule(ABC):
    @abstractmethod
    def declare_contract(self) -> SubstrateContract: ...

    @abstractmethod
    def handle(self, input: PerceptionInput) -> Emission: ...

    @abstractmethod
    def health(self) -> HealthReport: ...

    def justify(self, emission: Emission) -> JustificationToken | None:
        """Return a token iff the emission's action class requires justification.

        Returning None for a required class raises JustificationMissing (E-1).
        """
        return None

    def on_drain(self, deadline: datetime) -> None:
        """Optional. Complete or abandon in-flight work by deadline (E-3)."""
        return None


def run_handle(module: OrganismModule, input: PerceptionInput) -> Emission:
    """SDK handle path (SDK-4): call handle(), then justify(), validate token."""
    contract = module.declare_contract()
    emission = module.handle(input)
    required = set(contract.emission.requires_justification_for)
    if emission.action_class in required:
        token = module.justify(emission)
        if token is None:
            raise JustificationMissing(emission.action_class)
        if contract.justification.kind != JustificationKind.NONE and token.kind != contract.justification.kind:
            raise JustificationMissing(emission.action_class)
        return Emission(
            action_class=emission.action_class,
            payload=emission.payload,
            metadata=dict(emission.metadata),
            justification=token,
        )
    # Optional justify even if not required
    token = module.justify(emission)
    if token is not None:
        return Emission(
            action_class=emission.action_class,
            payload=emission.payload,
            metadata=dict(emission.metadata),
            justification=token,
        )
    return emission
