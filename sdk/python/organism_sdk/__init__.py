"""Organism Python authoring SDK — A3.1 + amendments (R-6, R-13, E-1, E-2, SDK-6)."""
from __future__ import annotations

from organism_sdk._proto_path import ensure_proto_path

ensure_proto_path()

__version__ = "0.1.0"

from organism_sdk.contract import (
    CapabilityScopes,
    EmissionSignature,
    FailureSignature,
    HealthEscalationPolicy,
    HealthHttp,
    HealthProbe,
    Identity,
    JustificationKind,
    JustificationSpec,
    Lifecycle,
    MetabolicProfile,
    ModuleRole,
    PerceptionSignature,
    ReliabilityTier,
    SafetyDeclaration,
    Shape,
    SubstrateContract,
    ValidationIssue,
)
from organism_sdk.errors import (
    JustificationMissing,
    ModalityUnavailable,
    RegistrationRejected,
    SDKInvariantViolation,
    TraceUnavailable,
)
from organism_sdk.health import HealthReport, HealthServer
from organism_sdk.hypervector import DIM, Hypervector
from organism_sdk.inputs import ModalityPayload, PerceptionInput, TaskDescriptor
from organism_sdk.justification import Emission, JustificationToken, VerificationResult
from organism_sdk.module import OrganismModule, run_handle
from organism_sdk.registry import CapabilityFilter, RegistryClient
from organism_sdk.trace import TraceEmitter
from organism_sdk.workspace import BindingRecord, WorkspaceClient

__all__ = [
    "DegradationMachine",
    "FaultInjector",
    "HealthSignals",

    "DIM",
    "BindingRecord",
    "CapabilityFilter",
    "CapabilityScopes",
    "Emission",
    "EmissionSignature",
    "FailureSignature",
    "HealthEscalationPolicy",
    "HealthHttp",
    "HealthProbe",
    "HealthReport",
    "HealthServer",
    "Hypervector",
    "Identity",
    "JustificationKind",
    "JustificationMissing",
    "JustificationSpec",
    "JustificationToken",
    "Lifecycle",
    "MetabolicProfile",
    "ModalityPayload",
    "ModalityUnavailable",
    "ModuleRole",
    "OrganismModule",
    "PerceptionInput",
    "PerceptionSignature",
    "RegistrationRejected",
    "RegistryClient",
    "ReliabilityTier",
    "SDKInvariantViolation",
    "SafetyDeclaration",
    "Shape",
    "SubstrateContract",
    "TaskDescriptor",
    "TraceEmitter",
    "TraceUnavailable",
    "ValidationIssue",
    "VerificationResult",
    "WorkspaceClient",
    "run_handle",
    "__version__",
]

from organism_sdk.degradation import DegradationMachine, FaultInjector, HealthSignals  # noqa: E402
