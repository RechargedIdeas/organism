"""SkillDescriptor + SkillRegistry — Organisms evolve skill packs via promote gates.

v1.7.1: skill pack versioning, dependency DAG, improve-from-trace (evolution_log),
promote requires shadow threshold.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from organism_sdk.generative.artifacts import ArtifactStore
from organism_sdk.generative.code_pipeline import CodeBundle, CodePipeline, PromoteRefused


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
    depends_on: tuple[str, ...] = ()
    shadow_score: float = 0.0
    version_history: list[dict[str, Any]] = field(default_factory=list)
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
            "depends_on": list(self.depends_on),
            "shadow_score": self.shadow_score,
            "version_history": list(self.version_history),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _bump_version(version: str) -> str:
    major_minor = version.split("-")[0]
    parts = major_minor.split(".")
    try:
        if len(parts) >= 3:
            patch = int(parts[-1]) + 1
            return f"{parts[0]}.{parts[1]}.{patch}"
        if len(parts) == 2:
            return f"{parts[0]}.{int(parts[1]) + 1}.0"
        return f"{parts[0]}.0.1"
    except ValueError:
        return version + "+1"


class SkillRegistry:
    """Attach / improve skill packs for an Organism identity."""

    def __init__(
        self,
        store: ArtifactStore | None = None,
        *,
        min_shadow_for_promote: float = 0.9,
    ) -> None:
        self.store = store
        self.min_shadow_for_promote = min_shadow_for_promote
        self._skills: dict[str, SkillDescriptor] = {}
        self._deps: dict[str, set[str]] = {}  # skill_id -> depends_on set
        self._lock = threading.RLock()

    def register(self, skill: SkillDescriptor) -> SkillDescriptor:
        with self._lock:
            # validate DAG edges reference known or declared ids (allow forward refs)
            for dep in skill.depends_on:
                if dep == skill.skill_id:
                    raise ValueError(f"skill {skill.skill_id} cannot depend on itself")
            # cycle check against known graph
            if self._would_cycle(skill.skill_id, skill.depends_on):
                raise ValueError(f"dependency cycle detected for {skill.skill_id}")
            prev = self._skills.get(skill.skill_id)
            if prev is not None:
                skill.version_history = list(prev.version_history) + [
                    {
                        "version": prev.version,
                        "source": prev.source,
                        "shadow_score": prev.shadow_score,
                        "at": prev.updated_at,
                    }
                ]
            self._skills[skill.skill_id] = skill
            self._deps[skill.skill_id] = set(skill.depends_on)
            self._persist(skill)
            return skill

    def _would_cycle(self, skill_id: str, depends_on: tuple[str, ...]) -> bool:
        """Return True if adding skill_id→deps creates a cycle."""
        graph = {k: set(v) for k, v in self._deps.items()}
        graph[skill_id] = set(depends_on)
        # DFS from skill_id following edges; cycle if we reach skill_id again
        stack = list(depends_on)
        seen: set[str] = set()
        while stack:
            n = stack.pop()
            if n == skill_id:
                return True
            if n in seen:
                continue
            seen.add(n)
            stack.extend(graph.get(n, ()))
        return False

    def get(self, skill_id: str) -> SkillDescriptor | None:
        return self._skills.get(skill_id)

    def list_skills(self) -> list[SkillDescriptor]:
        return list(self._skills.values())

    def as_dicts(self) -> list[dict[str, Any]]:
        return [s.as_dict() for s in self._skills.values()]

    def dependency_dag(self) -> dict[str, Any]:
        """Return nodes + edges for Desktop skill DAG view."""
        with self._lock:
            nodes = [
                {
                    "id": s.skill_id,
                    "name": s.name,
                    "version": s.version,
                    "may_control": s.may_control,
                    "shadow_score": s.shadow_score,
                    "source": s.source,
                }
                for s in self._skills.values()
            ]
            edges = []
            for sid, deps in self._deps.items():
                for d in deps:
                    edges.append({"from": d, "to": sid})
            # topological layers (best-effort)
            remaining = set(self._skills)
            layers: list[list[str]] = []
            satisfied: set[str] = set()
            while remaining:
                ready = [
                    sid
                    for sid in remaining
                    if self._deps.get(sid, set()).issubset(satisfied)
                ]
                if not ready:
                    # break cycles/unknown by dumping rest
                    layers.append(sorted(remaining))
                    break
                layers.append(sorted(ready))
                satisfied.update(ready)
                remaining -= set(ready)
            return {"nodes": nodes, "edges": edges, "layers": layers}

    def generate_skill(
        self,
        name: str,
        *,
        intent: str,
        code_pipeline: CodePipeline,
        tags: tuple[str, ...] = (),
        backend_name: str | None = None,
        auto_promote: bool = False,
        depends_on: tuple[str, ...] = (),
    ) -> tuple[SkillDescriptor, CodeBundle]:
        """Generate a skill pack via CodePipeline; RESEARCH_TIER until promoted."""
        from organism_sdk.generative.backends import resolve_backend

        backend = resolve_backend(backend_name)
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
            version="0.1.0",
            proficiency=min(1.0, max(0.0, bundle.shadow_score)),
            source="promoted" if bundle.may_control else "generated",
            tags=tags or ("generative",),
            code_bundle_id=bundle.bundle_id,
            research_tier=not bundle.may_control,
            may_control=bundle.may_control,
            description=intent[:400],
            depends_on=depends_on,
            shadow_score=bundle.shadow_score,
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
            depends_on=existing.depends_on,
        )
        skill.skill_id = existing.skill_id
        skill.version = _bump_version(existing.version)
        skill.source = "improved" if not bundle.may_control else "promoted"
        skill.updated_at = datetime.now(timezone.utc).isoformat()
        skill.shadow_score = bundle.shadow_score
        self.register(skill)
        return skill, bundle

    def improve_from_trace(
        self,
        skill_id: str,
        *,
        evolution_log: list[dict[str, Any]],
        code_pipeline: CodePipeline,
        auto_promote: bool = False,
    ) -> tuple[SkillDescriptor, CodeBundle]:
        """Improve a skill using recent evolution_log entries as intent context."""
        existing = self._skills.get(skill_id)
        if existing is None:
            raise KeyError(f"unknown skill_id={skill_id}")
        relevant = [
            e
            for e in evolution_log
            if e.get("kind") in ("skill_generate", "skill_improve", "skill_promote", "code_draft", "code_promote", "note")
            or (e.get("payload") or {}).get("skill_id") == skill_id
        ][-8:]
        summaries = [str(e.get("summary") or e.get("kind") or "") for e in relevant]
        trace_blob = " | ".join(summaries)[:600] or "no prior trace"
        intent = (
            f"Improve Organism skill {existing.name} v{existing.version} "
            f"from evolution_log: {trace_blob}"
        )
        skill, bundle = self.improve_skill(
            skill_id,
            intent=intent,
            code_pipeline=code_pipeline,
            auto_promote=auto_promote,
        )
        skill.tags = tuple(set(skill.tags) | {"from_trace"})
        skill.description = intent[:400]
        self.register(skill)
        return skill, bundle

    def attach_from_metamodel(self, organ: dict[str, Any]) -> SkillDescriptor:
        """Hook metamodel/NAS organ into skill registry as RESEARCH_TIER until promoted."""
        oid = str(organ.get("organ_id") or "metamodel_organ")
        skill = SkillDescriptor(
            skill_id=f"skill_mm_{oid[:12]}",
            name=f"metamodel:{oid}",
            version="0.1.0",
            proficiency=float(organ.get("shadow_pass_rate") or 0.0),
            source="metamodel",
            tags=("metamodel", "nas"),
            research_tier=organ.get("stage") != "PROMOTED",
            may_control=bool(organ.get("may_actuate")),
            description=f"Metamodel organ {oid}",
            shadow_score=float(organ.get("shadow_pass_rate") or 0.0),
        )
        return self.register(skill)

    def promote_skill(self, skill_id: str, *, code_pipeline: CodePipeline) -> SkillDescriptor:
        skill = self._skills.get(skill_id)
        if skill is None:
            raise KeyError(skill_id)
        if not skill.code_bundle_id:
            raise PermissionError("skill has no code bundle to promote")
        # v1.7.1: promote requires shadow threshold on the skill itself
        if skill.shadow_score < self.min_shadow_for_promote:
            # try to refresh from live bundle
            bundles = {b["bundle_id"]: b for b in code_pipeline.list_bundles()}
            live = bundles.get(skill.code_bundle_id)
            live_score = float((live or {}).get("shadow_score") or skill.shadow_score)
            skill.shadow_score = live_score
            if live_score < self.min_shadow_for_promote:
                raise PromoteRefused(
                    f"skill promote requires shadow_score>={self.min_shadow_for_promote}, "
                    f"got {live_score}"
                )
        bundle = code_pipeline.promote(skill.code_bundle_id)
        skill.may_control = bundle.may_control
        skill.research_tier = not bundle.may_control
        skill.source = "promoted"
        skill.proficiency = max(skill.proficiency, bundle.shadow_score)
        skill.shadow_score = max(skill.shadow_score, bundle.shadow_score)
        skill.version = _bump_version(skill.version)
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
            artifact_id=f"{skill.skill_id}_v{skill.version.replace('.', '_')}",
            metadata={
                "name": skill.name,
                "version": skill.version,
                "depends_on": list(skill.depends_on),
                "shadow_score": skill.shadow_score,
            },
            suffix=".json",
        )
