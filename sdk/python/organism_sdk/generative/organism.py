"""Organism identity — profile, skills, appearance, code revisions, evolution log."""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from organism_sdk.generative.assets import AppearanceProfile
from organism_sdk.generative.skills import SkillDescriptor


EvolutionKind = Literal[
    "code_draft",
    "code_promote",
    "code_demote",
    "code_rollback",
    "skill_generate",
    "skill_improve",
    "skill_promote",
    "looks_generate",
    "looks_apply",
    "looks_pack",
    "metamodel_attach",
    "note",
]


@dataclass
class EvolutionEvent:
    event_id: str
    kind: EvolutionKind
    summary: str
    at: str
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "summary": self.summary,
            "at": self.at,
            "payload": self.payload,
        }


@dataclass
class OrganismProfile:
    """Identity surface for a self-evolving Organism."""

    organism_id: str
    display_name: str = "Organism"
    skills: list[dict[str, Any]] = field(default_factory=list)
    appearance: dict[str, Any] = field(default_factory=dict)
    code_revisions: list[dict[str, Any]] = field(default_factory=list)
    evolution_log: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "organism_id": self.organism_id,
            "display_name": self.display_name,
            "skills": list(self.skills),
            "appearance": dict(self.appearance),
            "code_revisions": list(self.code_revisions),
            "evolution_log": list(self.evolution_log),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "skill_count": len(self.skills),
            "revision_count": len(self.code_revisions),
            "log_count": len(self.evolution_log),
        }


class OrganismStore:
    """Filesystem + in-memory Organism profiles."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._profiles: dict[str, OrganismProfile] = {}
        self._lock = threading.RLock()
        self._load_all()

    def _load_all(self) -> None:
        for path in self.root.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                p = OrganismProfile(**{k: raw[k] for k in OrganismProfile.__dataclass_fields__ if k in raw})
                self._profiles[p.organism_id] = p
            except Exception:
                continue

    def create(self, *, display_name: str = "Organism", organism_id: str | None = None) -> OrganismProfile:
        with self._lock:
            oid = organism_id or f"organism_{uuid.uuid4().hex[:12]}"
            profile = OrganismProfile(
                organism_id=oid,
                display_name=display_name,
                appearance=AppearanceProfile().as_dict(),
            )
            self._profiles[oid] = profile
            self._save(profile)
            return profile

    def get(self, organism_id: str) -> OrganismProfile | None:
        return self._profiles.get(organism_id)

    def ensure_default(self) -> OrganismProfile:
        if self._profiles:
            return next(iter(self._profiles.values()))
        return self.create(display_name="Primary Organism", organism_id="organism_primary")

    def list_profiles(self) -> list[OrganismProfile]:
        return list(self._profiles.values())

    def log(
        self,
        organism_id: str,
        kind: EvolutionKind,
        summary: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> EvolutionEvent:
        with self._lock:
            p = self._profiles.get(organism_id)
            if p is None:
                raise KeyError(organism_id)
            ev = EvolutionEvent(
                event_id=uuid.uuid4().hex[:12],
                kind=kind,
                summary=summary,
                at=datetime.now(timezone.utc).isoformat(),
                payload=payload or {},
            )
            p.evolution_log.append(ev.as_dict())
            p.updated_at = ev.at
            self._save(p)
            return ev

    def sync_skills(self, organism_id: str, skills: list[SkillDescriptor] | list[dict[str, Any]]) -> OrganismProfile:
        with self._lock:
            p = self._require(organism_id)
            p.skills = [s.as_dict() if hasattr(s, "as_dict") else dict(s) for s in skills]
            p.updated_at = datetime.now(timezone.utc).isoformat()
            self._save(p)
            return p

    def sync_appearance(self, organism_id: str, appearance: AppearanceProfile | dict[str, Any]) -> OrganismProfile:
        with self._lock:
            p = self._require(organism_id)
            p.appearance = appearance.as_dict() if hasattr(appearance, "as_dict") else dict(appearance)
            p.updated_at = datetime.now(timezone.utc).isoformat()
            self._save(p)
            return p

    def add_code_revision(self, organism_id: str, bundle: dict[str, Any]) -> OrganismProfile:
        with self._lock:
            p = self._require(organism_id)
            p.code_revisions.append(
                {
                    "bundle_id": bundle.get("bundle_id"),
                    "stage": bundle.get("stage"),
                    "may_control": bundle.get("may_control"),
                    "shadow_score": bundle.get("shadow_score"),
                    "shadow_metrics": bundle.get("shadow_metrics"),
                    "backend": bundle.get("backend"),
                    "stage_progress": bundle.get("stage_progress"),
                    "at": datetime.now(timezone.utc).isoformat(),
                }
            )
            p.updated_at = datetime.now(timezone.utc).isoformat()
            self._save(p)
            return p

    def _require(self, organism_id: str) -> OrganismProfile:
        p = self._profiles.get(organism_id)
        if p is None:
            raise KeyError(organism_id)
        return p

    def _save(self, profile: OrganismProfile) -> None:
        path = self.root / f"{profile.organism_id}.json"
        path.write_text(json.dumps(profile.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
