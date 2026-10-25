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
    "looks_theme_apply",
    "organism_switch",
    "organism_create",
    "bundle_export",
    "bundle_import",
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
    """Filesystem + in-memory Organism profiles with active selection (v1.8 multi-Organism)."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._profiles: dict[str, OrganismProfile] = {}
        self._active_id: str | None = None
        self._lock = threading.RLock()
        self._load_all()
        self._load_active()

    def _active_path(self) -> Path:
        return self.root / "_active.json"

    def _load_active(self) -> None:
        path = self._active_path()
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                aid = raw.get("active_id")
                if aid and aid in self._profiles:
                    self._active_id = aid
                    return
            except Exception:
                pass
        if self._profiles and self._active_id is None:
            self._active_id = next(iter(self._profiles))
            self._persist_active()

    def _persist_active(self) -> None:
        path = self._active_path()
        path.write_text(
            json.dumps({"active_id": self._active_id}, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _load_all(self) -> None:
        for path in self.root.glob("*.json"):
            if path.name.startswith("_"):
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                p = OrganismProfile(**{k: raw[k] for k in OrganismProfile.__dataclass_fields__ if k in raw})
                self._profiles[p.organism_id] = p
            except Exception:
                continue

    def create(self, *, display_name: str = "Organism", organism_id: str | None = None, make_active: bool = False) -> OrganismProfile:
        with self._lock:
            oid = organism_id or f"organism_{uuid.uuid4().hex[:12]}"
            if oid in self._profiles:
                raise ValueError(f"organism_id already exists: {oid}")
            profile = OrganismProfile(
                organism_id=oid,
                display_name=display_name,
                appearance=AppearanceProfile().as_dict(),
            )
            self._profiles[oid] = profile
            self._save(profile)
            if make_active or self._active_id is None:
                self._active_id = oid
                self._persist_active()
            return profile

    def get(self, organism_id: str) -> OrganismProfile | None:
        return self._profiles.get(organism_id)

    def active_id(self) -> str | None:
        return self._active_id

    def get_active(self) -> OrganismProfile | None:
        if self._active_id is None:
            return None
        return self._profiles.get(self._active_id)

    def set_active(self, organism_id: str) -> OrganismProfile:
        with self._lock:
            p = self._require(organism_id)
            self._active_id = organism_id
            self._persist_active()
            return p

    def switch(self, organism_id: str) -> OrganismProfile:
        """Alias for set_active — multi-Organism switch."""
        return self.set_active(organism_id)

    def ensure_default(self) -> OrganismProfile:
        with self._lock:
            if self._active_id and self._active_id in self._profiles:
                return self._profiles[self._active_id]
            if self._profiles:
                self._active_id = next(iter(self._profiles))
                self._persist_active()
                return self._profiles[self._active_id]
            return self.create(display_name="Primary Organism", organism_id="organism_primary", make_active=True)

    def list_profiles(self) -> list[OrganismProfile]:
        return list(self._profiles.values())

    def list_summaries(self) -> list[dict[str, Any]]:
        active = self._active_id
        out = []
        for p in self._profiles.values():
            d = {
                "organism_id": p.organism_id,
                "display_name": p.display_name,
                "skill_count": len(p.skills),
                "revision_count": len(p.code_revisions),
                "log_count": len(p.evolution_log),
                "active": p.organism_id == active,
                "updated_at": p.updated_at,
            }
            out.append(d)
        return out

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
