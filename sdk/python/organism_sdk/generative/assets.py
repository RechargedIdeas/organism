"""Generative asset pipeline — looks for Organisms (avatar/skin/icon/theme).

Procedural CPU-only generation + optional image backend stub. Assets stage
into an AppearanceProfile only after validate + promote-style apply.
"""
from __future__ import annotations

import colorsys
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from organism_sdk.generative.artifacts import ArtifactStore


AssetKind = Literal["avatar", "skin", "icon", "theme"]


class AssetStage(str, Enum):
    BRIEF = "BRIEF"
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    STAGED = "STAGED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"


@dataclass
class GeneratedAsset:
    asset_id: str
    kind: AssetKind
    brief: str
    stage: AssetStage = AssetStage.GENERATED
    width: int = 128
    height: int = 128
    format: str = "svg"
    body: str = ""
    safety_ok: bool = False
    dims_ok: bool = False
    path: str | None = None
    digest: str = ""
    research_tier: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "kind": self.kind,
            "brief": self.brief,
            "stage": self.stage.value,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "safety_ok": self.safety_ok,
            "dims_ok": self.dims_ok,
            "path": self.path,
            "digest": self.digest,
            "research_tier": self.research_tier,
            "body_preview": self.body[:240],
            "created_at": self.created_at,
        }


@dataclass
class AppearanceProfile:
    """Live Organism looks — only updated via AssetPipeline.apply."""

    avatar_id: str | None = None
    skin_id: str | None = None
    icon_id: str | None = None
    theme_id: str | None = None
    palette: dict[str, str] = field(default_factory=dict)
    revision: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "avatar_id": self.avatar_id,
            "skin_id": self.skin_id,
            "icon_id": self.icon_id,
            "theme_id": self.theme_id,
            "palette": dict(self.palette),
            "revision": self.revision,
        }


def _palette_from_brief(brief: str) -> dict[str, str]:
    h = int(hashlib.sha256(brief.encode()).hexdigest()[:6], 16) / float(0xFFFFFF)
    primary = colorsys.hsv_to_rgb(h, 0.55, 0.85)
    accent = colorsys.hsv_to_rgb((h + 0.35) % 1.0, 0.65, 0.9)
    bg = colorsys.hsv_to_rgb(h, 0.15, 0.18)

    def hexify(rgb: tuple[float, float, float]) -> str:
        return "#{:02x}{:02x}{:02x}".format(
            int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
        )

    return {
        "primary": hexify(primary),
        "accent": hexify(accent),
        "background": hexify(bg),
        "foreground": "#f2f2f2",
    }


def _svg_avatar(brief: str, *, w: int, h: int, palette: dict[str, str]) -> str:
    label = hashlib.sha256(brief.encode()).hexdigest()[:6].upper()
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}">'
        f'<rect width="100%" height="100%" fill="{palette["background"]}"/>'
        f'<circle cx="{w/2}" cy="{h/2}" r="{min(w,h)*0.35}" fill="{palette["primary"]}"/>'
        f'<circle cx="{w*0.4}" cy="{h*0.42}" r="{min(w,h)*0.05}" fill="{palette["foreground"]}"/>'
        f'<circle cx="{w*0.6}" cy="{h*0.42}" r="{min(w,h)*0.05}" fill="{palette["foreground"]}"/>'
        f'<path d="M {w*0.35} {h*0.58} Q {w/2} {h*0.72} {w*0.65} {h*0.58}" '
        f'fill="none" stroke="{palette["accent"]}" stroke-width="4"/>'
        f'<text x="{w/2}" y="{h-8}" text-anchor="middle" font-size="10" '
        f'fill="{palette["foreground"]}">{label}</text>'
        f"</svg>"
    )


def _svg_icon(brief: str, *, w: int, h: int, palette: dict[str, str]) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
        f'<rect rx="12" width="100%" height="100%" fill="{palette["primary"]}"/>'
        f'<polygon points="{w/2},12 {w-12},{h-12} 12,{h-12}" fill="{palette["accent"]}"/>'
        f"</svg>"
    )


def _theme_json(brief: str, palette: dict[str, str]) -> str:
    return json.dumps(
        {
            "name": f"theme_{hashlib.sha256(brief.encode()).hexdigest()[:8]}",
            "brief": brief[:200],
            "palette": palette,
            "cpu_only": True,
            "engine": "procedural_v1",
        },
        indent=2,
        sort_keys=True,
    )


_MAX_DIM = 1024
_MIN_DIM = 16
_FORBIDDEN_BRIEF = ("weaponize", "csam", "exploit payload")


class AssetPipeline:
    """brief → generate → validate dims/safety → stage → apply to AppearanceProfile."""

    def __init__(self, store: ArtifactStore, *, assets_root: Path | str | None = None) -> None:
        self.store = store
        self.assets_root = Path(assets_root) if assets_root else store.root / "assets"
        self.assets_root.mkdir(parents=True, exist_ok=True)
        self.assets: dict[str, GeneratedAsset] = {}
        self.appearance = AppearanceProfile()

    def generate(
        self,
        brief: str,
        *,
        kind: AssetKind = "avatar",
        width: int = 128,
        height: int = 128,
    ) -> GeneratedAsset:
        palette = _palette_from_brief(brief)
        digest = hashlib.sha256(f"{kind}:{brief}:{width}x{height}".encode()).hexdigest()
        asset_id = f"{kind}_{digest[:12]}"
        if kind == "theme":
            body = _theme_json(brief, palette)
            fmt = "json"
        elif kind == "icon":
            body = _svg_icon(brief, w=width, h=height, palette=palette)
            fmt = "svg"
        elif kind in ("avatar", "skin"):
            body = _svg_avatar(brief, w=width, h=height, palette=palette)
            fmt = "svg"
        else:
            raise ValueError(f"unknown asset kind {kind}")
        asset = GeneratedAsset(
            asset_id=asset_id,
            kind=kind,
            brief=brief,
            stage=AssetStage.GENERATED,
            width=width,
            height=height,
            format=fmt,
            body=body,
            digest=digest,
        )
        self.assets[asset_id] = asset
        return asset

    def validate(self, asset_id: str) -> GeneratedAsset:
        a = self._get(asset_id)
        brief_l = a.brief.lower()
        safety = not any(tok in brief_l for tok in _FORBIDDEN_BRIEF)
        dims = _MIN_DIM <= a.width <= _MAX_DIM and _MIN_DIM <= a.height <= _MAX_DIM
        if a.format == "svg" and "<svg" not in a.body:
            dims = False
        if a.format == "json":
            try:
                json.loads(a.body)
            except json.JSONDecodeError:
                dims = False
        a.safety_ok = safety
        a.dims_ok = dims
        if safety and dims:
            a.stage = AssetStage.VALIDATED
        else:
            a.stage = AssetStage.REJECTED
        return a

    def stage(self, asset_id: str) -> GeneratedAsset:
        a = self._get(asset_id)
        if a.stage != AssetStage.VALIDATED:
            raise PermissionError("stage requires VALIDATED asset")
        suffix = ".svg" if a.format == "svg" else ".json"
        path = self.assets_root / f"{a.asset_id}{suffix}"
        path.write_text(a.body, encoding="utf-8")
        manifest = {
            "asset_id": a.asset_id,
            "kind": a.kind,
            "digest": a.digest,
            "width": a.width,
            "height": a.height,
            "format": a.format,
            "path": str(path),
            "brief": a.brief[:500],
            "staged_at": datetime.now(timezone.utc).isoformat(),
            "research_tier": True,
        }
        man_path = self.assets_root / f"{a.asset_id}.manifest.json"
        man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        rec = self.store.put(
            kind="asset",
            body=a.body,
            backend="procedural_v1",
            stage=AssetStage.STAGED.value,
            artifact_id=a.asset_id,
            metadata=manifest,
            suffix=suffix,
        )
        a.path = str(path)
        a.stage = AssetStage.STAGED
        a.digest = rec.digest
        return a

    def apply(self, asset_id: str, appearance: AppearanceProfile | None = None) -> AppearanceProfile:
        """Apply staged asset to Organism appearance (looks evolution)."""
        a = self._get(asset_id)
        if a.stage not in (AssetStage.STAGED, AssetStage.APPLIED):
            raise PermissionError("apply requires STAGED asset")
        profile = appearance or self.appearance
        if a.kind == "avatar":
            profile.avatar_id = a.asset_id
        elif a.kind == "skin":
            profile.skin_id = a.asset_id
        elif a.kind == "icon":
            profile.icon_id = a.asset_id
        elif a.kind == "theme":
            profile.theme_id = a.asset_id
            try:
                profile.palette = json.loads(a.body).get("palette", {})
            except json.JSONDecodeError:
                profile.palette = _palette_from_brief(a.brief)
        profile.revision += 1
        a.stage = AssetStage.APPLIED
        a.research_tier = False
        self.appearance = profile
        self.store.put(
            kind="manifest",
            body=json.dumps(profile.as_dict(), indent=2),
            backend="procedural_v1",
            stage=AssetStage.APPLIED.value,
            artifact_id=f"appearance_{a.asset_id}",
            metadata={"applied_asset": a.asset_id},
            suffix=".json",
        )
        return profile

    def evolve_looks(
        self, brief: str, *, kind: AssetKind = "avatar", width: int = 128, height: int = 128
    ) -> dict[str, Any]:
        a = self.generate(brief, kind=kind, width=width, height=height)
        self.validate(a.asset_id)
        if a.stage == AssetStage.REJECTED:
            return {"ok": False, "asset": a.as_dict()}
        self.stage(a.asset_id)
        profile = self.apply(a.asset_id)
        return {"ok": True, "asset": a.as_dict(), "appearance": profile.as_dict()}

    def _get(self, asset_id: str) -> GeneratedAsset:
        if asset_id not in self.assets:
            raise KeyError(f"unknown asset_id={asset_id}")
        return self.assets[asset_id]

    def list_assets(self) -> list[dict[str, Any]]:
        return [a.as_dict() for a in self.assets.values()]
