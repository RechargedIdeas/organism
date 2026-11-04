"""Organism Python authoring SDK — A3.1 + amendments (R-6, R-13, E-1, E-2, SDK-6)."""
from __future__ import annotations

from organism_sdk._proto_path import ensure_proto_path

ensure_proto_path()

__version__ = "1.10.0"

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
    "DIM",
    "ApoptosisService",
    "AutonomicController",
    "BindingRecord",
    "CapabilityFilter",
    "CapabilityScopes",
    "CircadianClock",
    "DegradationMachine",
    "DevelopmentalGenome",
    "DevelopmentalStage",
    "Emission",
    "EmissionSignature",
    "FailureSignature",
    "FaultInjector",
    "HealthEscalationPolicy",
    "HealthHttp",
    "HealthProbe",
    "HealthReport",
    "HealthServer",
    "HealthSignals",
    "HealthVector",
    "HormoneBus",
    "HormoneLevels",
    "Hypervector",
    "Identity",
    "ImmuneLayer",
    "InteroceptiveStateEstimator",
    "JustificationKind",
    "JustificationMissing",
    "JustificationSpec",
    "JustificationToken",
    "Lifecycle",
    "MemoryExport",
    "MetabolicProfile",
    "ModalityPayload",
    "ModalityUnavailable",
    "ModuleRole",
    "MorphogenesisTracker",
    "OrganismModule",
    "PerceptionInput",
    "PerceptionSignature",
    "RegistrationRejected",
    "RegistryClient",
    "ReliabilityTier",
    "RouterExposedParams",
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
    "__version__",
    "kleiber_declared_share",
    "run_handle",
]

from organism_sdk.apoptosis import ApoptosisService, MemoryExport
from organism_sdk.autonomic import AutonomicController, RouterExposedParams
from organism_sdk.circadian import CircadianClock, kleiber_declared_share
from organism_sdk.degradation import DegradationMachine, FaultInjector, HealthSignals
from organism_sdk.hormone import HormoneBus, HormoneCoefficients, HormoneLevels
from organism_sdk.immune import ImmuneLayer
from organism_sdk.interoceptive import HealthVector, InteroceptiveStateEstimator
from organism_sdk.morphogenesis import DevelopmentalGenome, DevelopmentalStage, MorphogenesisTracker

