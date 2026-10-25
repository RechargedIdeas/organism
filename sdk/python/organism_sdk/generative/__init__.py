"""Organism generative evolution — code, assets, skills, Organism identity.

Production-grade pipelines so Organisms can self-evolve looks and skills.
Every path that can affect control or appearance goes through explicit promote
gates. Drafts are RESEARCH_TIER / exploration until promoted. CPU Everywhere;
no GPU hard-dep. Bio may_actuate remains False.

v1.7.1 hardenings: template library, GeneratorBackend protocol, replayable
drafts, expanded AST forbid list, shadow metrics, promote rollback, concurrent
ArtifactStore, multi-asset packs, content-hash integrity, skill DAG +
improve-from-trace.

v1.7.2: EvolutionRuntime hot-register, evolution traces, hormone pulse,
immune quarantine demote, wall-clock budgets.

v1.8.0: Desktop theme apply from looks, rollback deregisters GeneratedSkillModule,
multi-Organism store switch, export/import Organism bundles.
"""
from __future__ import annotations

from organism_sdk.generative.artifacts import ArtifactStore, IntegrityError, ProvenanceRecord
from organism_sdk.generative.assets import (
    AppearanceProfile,
    AssetKind,
    AssetPack,
    AssetPipeline,
    GeneratedAsset,
    contrast_ratio,
)
from organism_sdk.generative.backends import (
    DraftBackend,
    DraftReplayLog,
    GeneratorBackend,
    LLMStubBackend,
    TemplateDraftBackend,
    list_templates,
    resolve_backend,
)
from organism_sdk.generative.code_pipeline import (
    CodeBundle,
    CodePipeline,
    CodeStage,
    PromoteRefused,
    ShadowMetrics,
)
from organism_sdk.generative.organism import EvolutionEvent, OrganismProfile, OrganismStore
from organism_sdk.generative.theme import (
    DEFAULT_PALETTE,
    normalize_palette,
    shell_accent_qss,
    theme_apply_payload,
)
from organism_sdk.generative.bundle import (
    BUNDLE_FORMAT,
    export_organism_bundle,
    import_organism_bundle,
)
from organism_sdk.generative.runtime import (
    EVOLVE_P95_MS,
    HOT_REGISTER_P95_MS,
    PROMOTE_P95_MS,
    QUARANTINE_P95_MS,
    EvolutionRuntime,
    GeneratedSkillModule,
    HotRegisterResult,
    PipelineTiming,
    QuarantineResult,
)
from organism_sdk.generative.sandbox import SafeSandbox, SandboxRefused, SandboxResult
from organism_sdk.generative.skills import SkillDescriptor, SkillRegistry
from organism_sdk.generative.stages import EvolutionStage, PromoteGate

__all__ = [
    "ArtifactStore",
    "IntegrityError",
    "ProvenanceRecord",
    "AppearanceProfile",
    "AssetKind",
    "AssetPack",
    "AssetPipeline",
    "GeneratedAsset",
    "contrast_ratio",
    "DraftBackend",
    "DraftReplayLog",
    "GeneratorBackend",
    "LLMStubBackend",
    "TemplateDraftBackend",
    "list_templates",
    "resolve_backend",
    "CodeBundle",
    "CodePipeline",
    "CodeStage",
    "PromoteRefused",
    "ShadowMetrics",
    "EvolutionEvent",
    "OrganismProfile",
    "OrganismStore",
    "SafeSandbox",
    "SandboxRefused",
    "SandboxResult",
    "SkillDescriptor",
    "SkillRegistry",
    "EvolutionStage",
    "PromoteGate",
    "EVOLVE_P95_MS",
    "HOT_REGISTER_P95_MS",
    "DEFAULT_PALETTE",
    "normalize_palette",
    "shell_accent_qss",
    "theme_apply_payload",
    "BUNDLE_FORMAT",
    "export_organism_bundle",
    "import_organism_bundle",
    "PROMOTE_P95_MS",
    "QUARANTINE_P95_MS",
    "EvolutionRuntime",
    "GeneratedSkillModule",
    "HotRegisterResult",
    "PipelineTiming",
    "QuarantineResult",
]
