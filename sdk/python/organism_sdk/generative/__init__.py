"""Organism generative evolution — code, assets, skills, Organism identity.

Production-grade pipelines so Organisms can self-evolve looks and skills.
Every path that can affect control or appearance goes through explicit promote
gates. Drafts are RESEARCH_TIER / exploration until promoted. CPU Everywhere;
no GPU hard-dep. Bio may_actuate remains False.
"""
from __future__ import annotations

from organism_sdk.generative.artifacts import ArtifactStore, ProvenanceRecord
from organism_sdk.generative.assets import (
    AppearanceProfile,
    AssetKind,
    AssetPipeline,
    GeneratedAsset,
)
from organism_sdk.generative.backends import (
    DraftBackend,
    LLMStubBackend,
    TemplateDraftBackend,
)
from organism_sdk.generative.code_pipeline import (
    CodeBundle,
    CodePipeline,
    CodeStage,
    PromoteRefused,
)
from organism_sdk.generative.organism import EvolutionEvent, OrganismProfile, OrganismStore
from organism_sdk.generative.sandbox import SafeSandbox, SandboxResult
from organism_sdk.generative.skills import SkillDescriptor, SkillRegistry
from organism_sdk.generative.stages import EvolutionStage, PromoteGate

__all__ = [
    "ArtifactStore",
    "ProvenanceRecord",
    "AppearanceProfile",
    "AssetKind",
    "AssetPipeline",
    "GeneratedAsset",
    "DraftBackend",
    "LLMStubBackend",
    "TemplateDraftBackend",
    "CodeBundle",
    "CodePipeline",
    "CodeStage",
    "PromoteRefused",
    "EvolutionEvent",
    "OrganismProfile",
    "OrganismStore",
    "SafeSandbox",
    "SandboxResult",
    "SkillDescriptor",
    "SkillRegistry",
    "EvolutionStage",
    "PromoteGate",
]
