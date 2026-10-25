"""Organism export/import bundle — profile + skills + appearance + assets (v1.8).

Single zip: JSON manifests + asset bodies. Promote gates unchanged on import;
imported skills/code remain RESEARCH_TIER until explicitly re-promoted.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from organism_sdk.generative.assets import AppearanceProfile, AssetPipeline, GeneratedAsset, AssetStage
from organism_sdk.generative.organism import OrganismProfile, OrganismStore
from organism_sdk.generative.skills import SkillDescriptor, SkillRegistry


BUNDLE_FORMAT = "organism_bundle_v1"
BUNDLE_VERSION = "1.8.1"


@dataclass
class BundleManifest:
    format: str = BUNDLE_FORMAT
    version: str = BUNDLE_VERSION
    organism_id: str = ""
    display_name: str = ""
    exported_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    skill_count: int = 0
    asset_count: int = 0
    content_hash: str = ""
    may_actuate: bool = False
    cpu_everywhere: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "version": self.version,
            "organism_id": self.organism_id,
            "display_name": self.display_name,
            "exported_at": self.exported_at,
            "skill_count": self.skill_count,
            "asset_count": self.asset_count,
            "content_hash": self.content_hash,
            "may_actuate": self.may_actuate,
            "cpu_everywhere": self.cpu_everywhere,
        }


def _hash_blob(parts: list[bytes]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
    return h.hexdigest()


def export_organism_bundle(
    *,
    profile: OrganismProfile,
    skills: list[SkillDescriptor] | list[dict[str, Any]],
    appearance: AppearanceProfile | dict[str, Any],
    asset_pipeline: AssetPipeline | None,
    dest: Path | str,
) -> dict[str, Any]:
    """Write a zip at ``dest`` containing profile, skills, appearance, assets."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    appearance_d = appearance.as_dict() if hasattr(appearance, "as_dict") else dict(appearance)
    skill_dicts = [s.as_dict() if hasattr(s, "as_dict") else dict(s) for s in skills]
    assets_payload: list[dict[str, Any]] = []
    asset_bodies: dict[str, str] = {}

    if asset_pipeline is not None:
        ids = {
            appearance_d.get("avatar_id"),
            appearance_d.get("skin_id"),
            appearance_d.get("icon_id"),
            appearance_d.get("theme_id"),
        }
        ids.discard(None)
        for aid in ids:
            try:
                a = asset_pipeline.assets.get(aid)  # type: ignore[attr-defined]
            except Exception:
                a = None
            if a is None:
                continue
            assets_payload.append(a.as_dict())
            asset_bodies[aid] = a.body

    profile_json = json.dumps(profile.as_dict(), indent=2, sort_keys=True).encode()
    skills_json = json.dumps(skill_dicts, indent=2, sort_keys=True).encode()
    appearance_json = json.dumps(appearance_d, indent=2, sort_keys=True).encode()
    assets_json = json.dumps(assets_payload, indent=2, sort_keys=True).encode()
    content_hash = _hash_blob([profile_json, skills_json, appearance_json, assets_json])

    manifest = BundleManifest(
        organism_id=profile.organism_id,
        display_name=profile.display_name,
        skill_count=len(skill_dicts),
        asset_count=len(assets_payload),
        content_hash=content_hash,
    )
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest.as_dict(), indent=2, sort_keys=True))
        zf.writestr("organism_profile.json", profile_json)
        zf.writestr("skills.json", skills_json)
        zf.writestr("appearance.json", appearance_json)
        zf.writestr("assets/index.json", assets_json)
        for aid, body in asset_bodies.items():
            # Keep text bodies; theme is JSON, avatar/icon SVG.
            zf.writestr(f"assets/{aid}.body", body)

    return {
        "ok": True,
        "path": str(dest),
        "manifest": manifest.as_dict(),
        "bytes": dest.stat().st_size,
    }


def import_organism_bundle(
    *,
    path: Path | str,
    organism_store: OrganismStore,
    skill_registry: SkillRegistry,
    asset_pipeline: AssetPipeline,
    switch_active: bool = True,
    display_name_override: str | None = None,
) -> dict[str, Any]:
    """Import a bundle zip into store / skill registry / asset pipeline.

    Imported skills are forced RESEARCH_TIER / may_control=False until promote.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        required = {"manifest.json", "organism_profile.json", "skills.json", "appearance.json"}
        missing = required - names
        if missing:
            raise ValueError(f"invalid organism bundle; missing {sorted(missing)}")
        manifest = json.loads(zf.read("manifest.json"))
        if manifest.get("format") != BUNDLE_FORMAT:
            raise ValueError(f"unsupported bundle format: {manifest.get('format')!r}")
        profile_raw = json.loads(zf.read("organism_profile.json"))
        skills_raw = json.loads(zf.read("skills.json"))
        appearance_raw = json.loads(zf.read("appearance.json"))
        assets_index = []
        if "assets/index.json" in names:
            assets_index = json.loads(zf.read("assets/index.json"))
        bodies: dict[str, str] = {}
        for name in names:
            if name.startswith("assets/") and name.endswith(".body"):
                aid = Path(name).name[: -len(".body")]
                bodies[aid] = zf.read(name).decode("utf-8")

    oid = profile_raw.get("organism_id") or f"organism_import_{manifest.get('content_hash', 'x')[:10]}"
    display = display_name_override or profile_raw.get("display_name") or "Imported Organism"
    existing = organism_store.get(oid)
    if existing is None:
        profile = organism_store.create(display_name=display, organism_id=oid)
    else:
        profile = existing
        profile.display_name = display

    # Restore skills as RESEARCH_TIER drafts (never auto-promote on import).
    imported_skills: list[str] = []
    for raw in skills_raw:
        if not isinstance(raw, dict):
            continue
        deps = raw.get("depends_on") or ()
        if isinstance(deps, list):
            deps = tuple(deps)
        skill = SkillDescriptor(
            skill_id=str(raw.get("skill_id") or f"imported_{len(imported_skills)}"),
            name=str(raw.get("name") or "imported"),
            description=str(raw.get("description") or "imported skill"),
            version=str(raw.get("version") or "0.1.0"),
            proficiency=float(raw.get("proficiency") or 0.0),
            shadow_score=float(raw.get("shadow_score") or 0.0),
            source="generated",
            depends_on=tuple(deps),
            code_bundle_id=raw.get("code_bundle_id"),
            may_control=False,
            research_tier=True,
            version_history=list(raw.get("version_history") or []),
            tags=tuple(raw.get("tags") or ()),
        )
        skill_registry.register(skill)
        imported_skills.append(skill.skill_id)

    # Restore assets into pipeline memory (bodies optional).
    restored_assets: list[str] = []
    for meta in assets_index:
        aid = meta.get("asset_id")
        if not aid:
            continue
        body = bodies.get(aid, meta.get("body_preview") or "")
        kind = meta.get("kind") or "avatar"
        asset = GeneratedAsset(
            asset_id=aid,
            kind=kind,
            brief=str(meta.get("brief") or "imported"),
            stage=AssetStage.STAGED,
            width=int(meta.get("width") or 128),
            height=int(meta.get("height") or 128),
            format=str(meta.get("format") or ("json" if kind == "theme" else "svg")),
            body=body,
            safety_ok=True,
            dims_ok=True,
            size_ok=True,
            contrast_ok=True,
            content_hash=str(meta.get("content_hash") or ""),
            research_tier=True,
        )
        asset_pipeline.assets[aid] = asset
        restored_assets.append(aid)

    # Apply appearance (palette only if theme body present).
    app = AppearanceProfile(
        avatar_id=appearance_raw.get("avatar_id"),
        skin_id=appearance_raw.get("skin_id"),
        icon_id=appearance_raw.get("icon_id"),
        theme_id=appearance_raw.get("theme_id"),
        pack_id=appearance_raw.get("pack_id"),
        palette=dict(appearance_raw.get("palette") or {}),
        revision=int(appearance_raw.get("revision") or 0),
    )
    # If theme body is JSON with palette, prefer it.
    if app.theme_id and app.theme_id in asset_pipeline.assets:
        try:
            theme_body = json.loads(asset_pipeline.assets[app.theme_id].body)
            if isinstance(theme_body.get("palette"), dict):
                app.palette = dict(theme_body["palette"])
        except Exception:
            pass
    asset_pipeline.appearance = app
    organism_store.sync_appearance(oid, app)
    organism_store.sync_skills(oid, skill_registry.list_skills())
    # Carry over evolution_log + code_revisions from export when present.
    with organism_store._lock:
        p = organism_store._require(oid)
        if profile_raw.get("evolution_log"):
            p.evolution_log = list(profile_raw["evolution_log"])
        if profile_raw.get("code_revisions"):
            p.code_revisions = list(profile_raw["code_revisions"])
        p.updated_at = datetime.now(timezone.utc).isoformat()
        organism_store._save(p)
    organism_store.log(
        oid,
        "note",
        f"Imported Organism bundle from {path.name}",
        payload={
            "manifest": manifest,
            "skills": imported_skills,
            "assets": restored_assets,
        },
    )
    if switch_active:
        organism_store.set_active(oid)
    profile = organism_store.get(oid)
    assert profile is not None
    return {
        "ok": True,
        "organism_id": oid,
        "display_name": profile.display_name,
        "skills_imported": imported_skills,
        "assets_restored": restored_assets,
        "appearance": app.as_dict(),
        "active": organism_store.active_id(),
        "manifest": manifest,
        "may_actuate": False,
    }
