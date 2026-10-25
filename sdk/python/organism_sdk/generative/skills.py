"""SkillDescriptor + SkillRegistry — Organisms evolve skill packs via promote gates."""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from organism_sdk.generative.artifacts import ArtifactStore
from organism_sdk.generative.code_pipeline import CodeBundle, CodePipeline


SkillSource = Literal["seed", "generated", "improved", "promoted", "metamodel"]


@dataclass
class SkillDescriptor:
    skill_id: str
    name: str
    version: str = "0.1.0"
    proficiency: float = 0.0
    source: SkillSource = "seed"
    tags: tuple[str, ...] = ()
    code_bundle_id: str | None = None
    research_tier: bool = True
    may_control: bool = False
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "version": self.version,
            "proficiency": self.proficiency,
            "source": self.source,
            "tags": list(self.tags),
            "code_bundle_id": self.code_bundle_id,
            "research_tier": self.research_tier,
            "may_control": self.may_control,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SkillRegistry:
    """Attach / improve skill packs for an Organism identity."""

    def __init__(self, store: ArtifactStore | None = None) -> None:
        self.store = store
        self._skills: dict[str, SkillDescriptor] = {}
        self._lock = threading.RLock()

    def register(self, skill: SkillDescriptor) -> SkillDescriptor:
        with self._lock:
            self._skills[skill.skill_id] = skill
            self._persist(skill)
            return skill

    def get(self, skill_id: str) -> SkillDescriptor | None:
        return self._skills.get(skill_id)

    def list_skills(self) -> list[SkillDescriptor]:
        return list(self._skills.values())

    def as_dicts(self) -> list[dict[str, Any]]:
        return [s.as_dict() for s in self._skills.values()]

    def generate_skill(
        self,
        name: str,
        *,
        intent: str,
        code_pipeline: CodePipeline,
        tags: tuple[str, ...] = (),
        backend_name: str | None = None,
        auto_promote: bool = False,
    ) -> tuple[SkillDescriptor, CodeBundle]:
        """Generate a skill pack via CodePipeline; RESEARCH_TIER until promoted."""
        from organism_sdk.generative.backends import LLMStubBackend, TemplateDraftBackend

        backend = None
        if backend_name == "llm_stub":
            backend = LLMStubBackend()
        elif backend_name == "template" or backend_name is None:
            backend = TemplateDraftBackend()
        bundle = code_pipeline.evolve(
            intent,
            spec={"skill_name": name, "may_actuate": False},
            backend=backend,
            auto_promote=auto_promote,
        )
        sid = f"skill_{hashlib.sha256(name.encode()).hexdigest()[:10]}"
        skill = SkillDescriptor(
            skill_id=sid,
            name=name,
            version="0.1.0-gen",
            proficiency=min(1.0, max(0.0, bundle.shadow_score)),
            source="promoted" if bundle.may_control else "generated",
            tags=tags or ("generative",),
            code_bundle_id=bundle.bundle_id,
            research_tier=not bundle.may_control,
            may_control=bundle.may_control,
            description=intent[:400],
        )
        self.register(skill)
        return skill, bundle

    def improve_skill(
        self,
        skill_id: str,
        *,
        intent: str,
        code_pipeline: CodePipeline,
        auto_promote: bool = False,
    ) -> tuple[SkillDescriptor, CodeBundle]:
        existing = self._skills.get(skill_id)
        if existing is None:
            raise KeyError(f"unknown skill_id={skill_id}")
        skill, bundle = self.generate_skill(
            existing.name,
            intent=intent,
            code_pipeline=code_pipeline,
            tags=tuple(set(existing.tags) | {"improved"}),
            auto_promote=auto_promote,
        )
        # version bump semantics
        skill.skill_id = existing.skill_id
        major_minor = existing.version.split("-")[0]
        parts = major_minor.split(".")
        try:
            patch = int(parts[-1]) + 1 if len(parts) >= 3 else 1
            skill.version = f"{parts[0]}.{parts[1] if len(parts)>1 else '0'}.{patch}-gen"
        except ValueError:
            skill.version = existing.version + "+1"
        skill.source = "improved" if not bundle.may_control else "promoted"
        skill.updated_at = datetime.now(timezone.utc).isoformat()
        self.register(skill)
        return skill, bundle

    def attach_from_metamodel(self, organ: dict[str, Any]) -> SkillDescriptor:
        """Hook metamodel/NAS organ into skill registry as RESEARCH_TIER until promoted."""
        oid = str(organ.get("organ_id") or "metamodel_organ")
        skill = SkillDescriptor(
            skill_id=f"skill_mm_{oid[:12]}",
            name=f"metamodel:{oid}",
            version="0.1.0-mm",
            proficiency=float(organ.get("shadow_pass_rate") or 0.0),
            source="metamodel",
            tags=("metamodel", "nas"),
            research_tier=organ.get("stage") != "PROMOTED",
            may_control=bool(organ.get("may_actuate")),
            description=f"Metamodel organ {oid}",
        )
        return self.register(skill)

    def promote_skill(self, skill_id: str, *, code_pipeline: CodePipeline) -> SkillDescriptor:
        skill = self._skills.get(skill_id)
        if skill is None:
            raise KeyError(skill_id)
        if not skill.code_bundle_id:
            raise PermissionError("skill has no code bundle to promote")
        bundle = code_pipeline.promote(skill.code_bundle_id)
        skill.may_control = bundle.may_control
        skill.research_tier = not bundle.may_control
        skill.source = "promoted"
        skill.proficiency = max(skill.proficiency, bundle.shadow_score)
        skill.updated_at = datetime.now(timezone.utc).isoformat()
        self.register(skill)
        return skill

    def _persist(self, skill: SkillDescriptor) -> None:
        if self.store is None:
            return
        self.store.put(
            kind="skill",
            body=json.dumps(skill.as_dict(), indent=2, sort_keys=True),
            backend="skill_registry",
            stage=skill.source,
            artifact_id=skill.skill_id,
            metadata={"name": skill.name},
            suffix=".json",
        )
