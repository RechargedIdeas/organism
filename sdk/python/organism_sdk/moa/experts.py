"""MoA experts: capability descriptors, the expert base class, and registration (v1.11).

An expert answers one query in one of the structural router's task forms and
reports a confidence and whether its payload is well-formed. Experts register in
the existing registry as contracts with ``may_actuate=False`` and reliability
tier T0. The MoA pipeline (``pipeline.py``) decides which experts run.

Experts follow the registry's health protocol (``health() -> HealthReport``)
but do not implement ``OrganismModule.handle``. They are routed by the MoA
pipeline, not by the structural router's dispatch path.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from organism_sdk.contract import (
    BudgetClass,
    CapabilityScopes,
    DataType,
    DegradationKind,
    Determinism,
    EmissionSignature,
    EscalationKind,
    FailureMode,
    FailureSignature,
    HardwareRequirement,
    HealthEscalationPolicy,
    HealthProbe,
    HealthRpc,
    Identity,
    Lifecycle,
    MaxSafetyTier,
    MetabolicProfile,
    Modality,
    ModuleRole,
    OutputForm,
    PerceptionSignature,
    RecoveryKind,
    RecoveryProcedure,
    ReliabilityTier,
    ResourceVector,
    SafetyDeclaration,
    Shape,
    SubstrateContract,
    UncertaintyKind,
)
from organism_sdk.health import HealthReport
from organism_sdk.registry import RegisterResponse, RegistryClient
from organism_sdk.router import DEFAULT_FORM_TO_ROLES

HEALTHY = "HEALTHY"
FAILED = "FAILED"

EXPERT_VERSION = "0.1.0"
EXPERT_AUTHOR = "organism-ref"
EXPERT_LICENSE = "Apache-2.0"
HEALTH_METHOD_FQN = "organism.moa.Expert/Health"


@dataclass(frozen=True)
class CuedKeyword:
    """A phrase that counts for an expert only when the query also has one of its cue words (O4).

    "email address" alone is ambiguous. "Set up an email address" is not an extraction request,
    but "pull the email address out of this" is. The phrase counts only beside a verb of retrieval,
    so a cue word with no phrase has no effect, and "find" cannot pull in a query that has no phrase.
    """

    phrase: str
    cues: tuple[str, ...]


@dataclass(frozen=True)
class CapabilityDescriptor:
    """What an expert claims it can answer. The router's decision input."""

    expert_id: str
    domain: str
    task_forms: tuple[str, ...]
    keywords: tuple[str, ...]
    role: ModuleRole
    expected_latency_ms: float = 5.0
    requires_gpu: bool = False
    version: str = EXPERT_VERSION
    cued_keywords: tuple[CuedKeyword, ...] = ()

    def __post_init__(self) -> None:
        if not self.expert_id or not self.domain:
            raise ValueError("expert_id and domain are required")
        if not self.keywords:
            raise ValueError(f"{self.expert_id}: at least one keyword is required")
        for cued in self.cued_keywords:
            if not cued.phrase or not cued.cues:
                raise ValueError(f"{self.expert_id}: a cued keyword needs a phrase and cues")
        if not self.task_forms:
            raise ValueError(f"{self.expert_id}: at least one task form is required")
        for form in self.task_forms:
            if form not in DEFAULT_FORM_TO_ROLES:
                raise ValueError(f"{self.expert_id}: unknown task form {form!r}")
            if self.role.value not in DEFAULT_FORM_TO_ROLES[form]:
                raise ValueError(
                    f"{self.expert_id}: role {self.role.value} is not eligible for form {form!r}"
                )
        if self.expected_latency_ms <= 0:
            raise ValueError(f"{self.expert_id}: expected_latency_ms must be positive")


@dataclass(frozen=True)
class ExpertOutput:
    """One expert's answer to one query."""

    expert_id: str
    payload: str
    confidence: float
    schema_valid: bool

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")


class Expert(Protocol):
    @property
    def descriptor(self) -> CapabilityDescriptor: ...

    def health(self) -> HealthReport: ...

    def answer(self, query: str, form: str | None = None) -> ExpertOutput: ...


class BaseExpert:
    """Shared health state and contract declaration for in-process experts."""

    def __init__(self, descriptor: CapabilityDescriptor) -> None:
        self._descriptor = descriptor
        self._status = HEALTHY

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return self._descriptor

    @property
    def status(self) -> str:
        return self._status

    def fail(self) -> None:
        self._status = FAILED

    def restore(self) -> None:
        self._status = HEALTHY

    def health(self) -> HealthReport:
        return HealthReport(module_id=self.module_id, status=self._status, score=1.0 if self._status == HEALTHY else 0.0)

    @property
    def module_id(self) -> str:
        return f"moa.{self._descriptor.expert_id}"

    def answer(self, query: str, form: str | None = None) -> ExpertOutput:  # pragma: no cover - abstract
        raise NotImplementedError

    def declare_contract(self) -> SubstrateContract:
        d = self._descriptor
        digest = hashlib.sha256(f"{self.module_id}:{d.version}".encode()).digest()
        return SubstrateContract(
            identity=Identity(
                module_id=self.module_id,
                version=d.version,
                author=EXPERT_AUTHOR,
                license=EXPERT_LICENSE,
                role=d.role,
                artifact_digest=digest,
            ),
            perception=PerceptionSignature(
                modalities=(Modality.TEXT,),
                required_modalities=(Modality.TEXT,),
                shapes={"TEXT": Shape(dims=(1,), dtype=DataType.INT64)},
            ),
            emission=EmissionSignature(
                output_form=OutputForm.SYMBOLIC_TRIPLE,
                shape=Shape(dims=(3,), dtype=DataType.INT64),
                uncertainty=UncertaintyKind.NONE,
                determinism=Determinism.DETERMINISTIC,
                requires_justification_for=(),
            ),
            metabolic=MetabolicProfile(
                latency_p50_ms=d.expected_latency_ms,
                latency_p95_ms=2 * d.expected_latency_ms,
                latency_p99_ms=4 * d.expected_latency_ms,
                energy_per_inference_j=0.001,
                memory_footprint_mb=8.0,
                memory_peak_mb=16.0,
                metabolic_budget_class=BudgetClass.LEAN,
                declared_share=ResourceVector(cpu_cores=0.1, memory_mb=16.0),
                # The contract has no GPU enum; requires_gpu lives on the descriptor
                # and drives the MoA tier logic instead.
                requires_special_hardware=HardwareRequirement.NONE,
            ),
            failure=FailureSignature(
                modes=(
                    FailureMode(
                        name="crash",
                        observable_signal="expert.health",
                        expected_degradation=DegradationKind.CRASH,
                        detection_latency_budget_ms=500.0,
                    ),
                ),
                probe=HealthProbe(HealthRpc(method_fqn=HEALTH_METHOD_FQN, timeout_ms=200)),
                recovery=RecoveryProcedure(kind=RecoveryKind.RESTART, max_attempts=3),
                escalation=HealthEscalationPolicy(
                    kind=EscalationKind.PROBE_OR_DURATION,
                    consecutive_probe_failures=2,
                    degraded_duration_ms=5000,
                    escalate_on_probe_timeout=True,
                    escalate_on_probe_unreachable=False,
                    probe_interval_ms=1000,
                ),
            ),
            safety=SafetyDeclaration(
                reliability_tier=ReliabilityTier.T0_DETERMINISTIC,
                may_actuate=False,
                requires_causal_certificate=False,
                requires_cross_check=False,
                max_safety_tier=MaxSafetyTier.LOW,
            ),
            lifecycle=Lifecycle(hot_swap_supported=True, shadow_validation_required=True),
            capabilities=CapabilityScopes(
                read_roles=(d.role.value.lower(),),
                write_roles=(),
                read_tags=(d.domain,),
                write_tags=(),
                can_emit_control_affecting=False,
            ),
        )


def register_experts(
    registry: RegistryClient,
    experts: list[BaseExpert],
    *,
    initial_state: str = "EXPLORATION",
) -> list[RegisterResponse]:
    """Register each expert's contract with the registry. Rejects invalid contracts."""
    responses = []
    for expert in experts:
        contract = expert.declare_contract()
        digest = hashlib.sha256(contract.identity.module_id.encode() + b"reference").digest()
        responses.append(
            registry.register(
                contract,
                artifact_digest=digest,
                author_signature=b"reference-unsigned",
                module=expert,
                initial_state=initial_state,  # type: ignore[arg-type]
            )
        )
    return responses


__all__ = [
    "FAILED",
    "HEALTHY",
    "BaseExpert",
    "CapabilityDescriptor",
    "Expert",
    "ExpertOutput",
    "register_experts",
]
