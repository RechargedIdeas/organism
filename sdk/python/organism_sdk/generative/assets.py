"""Generative asset pipeline — looks for Organisms (avatar/skin/icon/theme).

v1.7.1: multi-asset packs, content-hash integrity, preview bytes, oversized /
malformed rejection, theme contrast checks. Procedural CPU-only generation.
"""
from __future__ import annotations

import colorsys
import hashlib
import json
import math
import threading
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


_MAX_DIM = 1024
_MIN_DIM = 16
_MAX_BODY_BYTES = 256_000  # reject oversized
_FORBIDDEN_BRIEF = ("weaponize", "csam", "exploit payload")
_MIN_CONTRAST = 3.0  # WCAG-ish floor for theme fg/bg


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
    size_ok: bool = False
    contrast_ok: bool = True
    content_hash: str = ""
    path: str | None = None
    digest: str = ""
    research_tier: bool = True
    preview_bytes: bytes = b""
    validation_errors: list[str] = field(default_factory=list)
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
            "size_ok": self.size_ok,
            "contrast_ok": self.contrast_ok,
            "content_hash": self.content_hash,
            "path": self.path,
            "digest": self.digest,
            "research_tier": self.research_tier,
            "body_preview": self.body[:240],
            "preview_b64_len": len(self.preview_bytes),
            "validation_errors": list(self.validation_errors),
            "created_at": self.created_at,
        }


@dataclass
class AppearanceProfile:
    """Live Organism looks — only updated via AssetPipeline.apply / apply_pack."""

    avatar_id: str | None = None
    skin_id: str | None = None
    icon_id: str | None = None
    theme_id: str | None = None
    pack_id: str | None = None
    palette: dict[str, str] = field(default_factory=dict)
    revision: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "avatar_id": self.avatar_id,
            "skin_id": self.skin_id,
            "icon_id": self.icon_id,
            "theme_id": self.theme_id,
            "pack_id": self.pack_id,
            "palette": dict(self.palette),
            "revision": self.revision,
        }


@dataclass
class AssetPack:
    """Multi-asset pack: avatar SVG + theme JSON + icon (v1.7.1)."""

    pack_id: str
    brief: str
    asset_ids: dict[str, str] = field(default_factory=dict)
    content_hash: str = ""
    stage: str = "GENERATED"
    research_tier: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "brief": self.brief,
            "asset_ids": dict(self.asset_ids),
            "content_hash": self.content_hash,
            "stage": self.stage,
            "research_tier": self.research_tier,
            "created_at": self.created_at,
        }


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    if len(h) != 6:
        return (0.0, 0.0, 0.0)
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)


def _rel_luminance(rgb: tuple[float, float, float]) -> float:
    def chan(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (chan(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    l1 = _rel_luminance(_hex_to_rgb(fg))
    l2 = _rel_luminance(_hex_to_rgb(bg))
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _palette_from_brief(brief: str) -> dict[str, str]:
    h = int(hashlib.sha256(brief.encode()).hexdigest()[:6], 16) / float(0xFFFFFF)
    primary = colorsys.hsv_to_rgb(h, 0.55, 0.85)
    accent = colorsys.hsv_to_rgb((h + 0.35) % 1.0, 0.65, 0.9)
    bg = colorsys.hsv_to_rgb(h, 0.15, 0.18)

    def hexify(rgb: tuple[float, float, float]) -> str:
        return "#{:02x}{:02x}{:02x}".format(
            int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
        )

    palette = {
        "primary": hexify(primary),
        "accent": hexify(accent),
        "background": hexify(bg),
        "foreground": "#f2f2f2",
    }
    # Ensure contrast meets floor by forcing light fg on dark bg when needed.
    if contrast_ratio(palette["foreground"], palette["background"]) < _MIN_CONTRAST:
        palette["foreground"] = "#ffffff"
        palette["background"] = "#121212"
    return palette


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
    ratio = contrast_ratio(palette["foreground"], palette["background"])
    return json.dumps(
        {
            "name": f"theme_{hashlib.sha256(brief.encode()).hexdigest()[:8]}",
            "brief": brief[:200],
            "palette": palette,
            "contrast_ratio": round(ratio, 3),
            "cpu_only": True,
            "engine": "procedural_v1.7.1",
        },
        indent=2,
        sort_keys=True,
    )


def _preview_bytes(body: str, *, max_len: int = 4096) -> bytes:
    data = body.encode("utf-8")
    return data[:max_len]


class AssetPipeline:
    """brief → generate → validate dims/safety/size/contrast → stage → apply."""

    def __init__(self, store: ArtifactStore, *, assets_root: Path | str | None = None) -> None:
        self.store = store
        self.assets_root = Path(assets_root) if assets_root else store.root / "assets"
        self.assets_root.mkdir(parents=True, exist_ok=True)
        self.assets: dict[str, GeneratedAsset] = {}
        self.packs: dict[str, AssetPack] = {}
        self.appearance = AppearanceProfile()
        self._lock = threading.RLock()

    def generate(
        self,
        brief: str,
        *,
        kind: AssetKind = "avatar",
        width: int = 128,
        height: int = 128,
        body_override: str | None = None,
    ) -> GeneratedAsset:
        with self._lock:
            palette = _palette_from_brief(brief)
            digest = hashlib.sha256(f"{kind}:{brief}:{width}x{height}".encode()).hexdigest()
            asset_id = f"{kind}_{digest[:12]}"
            if body_override is not None:
                body = body_override
                fmt = "svg" if kind != "theme" else "json"
            elif kind == "theme":
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
            content_hash = hashlib.sha256(body.encode()).hexdigest()
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
                content_hash=content_hash,
                preview_bytes=_preview_bytes(body),
            )
            self.assets[asset_id] = asset
            return asset

    def validate(self, asset_id: str) -> GeneratedAsset:
        with self._lock:
            a = self._get(asset_id)
            errs: list[str] = []
            brief_l = a.brief.lower()
            safety = not any(tok in brief_l for tok in _FORBIDDEN_BRIEF)
            if not safety:
                errs.append("safety: forbidden brief token")
            dims = _MIN_DIM <= a.width <= _MAX_DIM and _MIN_DIM <= a.height <= _MAX_DIM
            if not dims:
                errs.append(f"dims: {a.width}x{a.height} out of [{_MIN_DIM},{_MAX_DIM}]")
            body_bytes = len(a.body.encode("utf-8"))
            size_ok = body_bytes <= _MAX_BODY_BYTES
            if not size_ok:
                errs.append(f"size: {body_bytes} bytes exceeds {_MAX_BODY_BYTES}")
            contrast_ok = True
            if a.format == "svg":
                if "<svg" not in a.body or "</svg>" not in a.body:
                    dims = False
                    errs.append("malformed: svg missing tags")
                if "<script" in a.body.lower():
                    safety = False
                    errs.append("safety: script tag in svg")
            if a.format == "json":
                try:
                    parsed = json.loads(a.body)
                    if not isinstance(parsed, dict):
                        dims = False
                        errs.append("malformed: theme JSON must be object")
                    else:
                        pal = parsed.get("palette") or {}
                        fg = pal.get("foreground", "#fff")
                        bg = pal.get("background", "#000")
                        ratio = contrast_ratio(str(fg), str(bg))
                        contrast_ok = ratio >= _MIN_CONTRAST
                        if not contrast_ok:
                            errs.append(f"contrast: ratio {ratio:.2f} < {_MIN_CONTRAST}")
                except json.JSONDecodeError as e:
                    dims = False
                    errs.append(f"malformed: json {e}")
            # content-hash integrity of in-memory body
            actual = hashlib.sha256(a.body.encode()).hexdigest()
            if a.content_hash and actual != a.content_hash:
                safety = False
                errs.append("integrity: content-hash mismatch")
            a.safety_ok = safety
            a.dims_ok = dims
            a.size_ok = size_ok
            a.contrast_ok = contrast_ok
            a.validation_errors = errs
            a.preview_bytes = _preview_bytes(a.body)
            if safety and dims and size_ok and contrast_ok:
                a.stage = AssetStage.VALIDATED
            else:
                a.stage = AssetStage.REJECTED
            return a

    def stage(self, asset_id: str) -> GeneratedAsset:
        with self._lock:
            a = self._get(asset_id)
            if a.stage != AssetStage.VALIDATED:
                raise PermissionError("stage requires VALIDATED asset")
            suffix = ".svg" if a.format == "svg" else ".json"
            path = self.assets_root / f"{a.asset_id}{suffix}"
            path.write_text(a.body, encoding="utf-8")
            # re-hash after write for integrity record
            on_disk = path.read_bytes()
            content_hash = hashlib.sha256(on_disk).hexdigest()
            a.content_hash = content_hash
            manifest = {
                "asset_id": a.asset_id,
                "kind": a.kind,
                "digest": a.digest,
                "content_hash": content_hash,
                "width": a.width,
                "height": a.height,
                "format": a.format,
                "path": str(path),
                "brief": a.brief[:500],
                "staged_at": datetime.now(timezone.utc).isoformat(),
                "research_tier": True,
                "preview_len": len(a.preview_bytes),
            }
            man_path = self.assets_root / f"{a.asset_id}.manifest.json"
            man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            rec = self.store.put(
                kind="asset",
                body=a.body,
                backend="procedural_v1.7.1",
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
        with self._lock:
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
                backend="procedural_v1.7.1",
                stage=AssetStage.APPLIED.value,
                artifact_id=f"appearance_{a.asset_id}",
                metadata={"applied_asset": a.asset_id, "content_hash": a.content_hash},
                suffix=".json",
            )
            return profile

    def generate_pack(self, brief: str, *, width: int = 128, height: int = 128) -> AssetPack:
        """Generate avatar + theme + icon as one multi-asset pack."""
        with self._lock:
            avatar = self.generate(brief, kind="avatar", width=width, height=height)
            theme = self.generate(brief, kind="theme", width=width, height=height)
            icon = self.generate(f"{brief} icon", kind="icon", width=width, height=height)
            ids = {"avatar": avatar.asset_id, "theme": theme.asset_id, "icon": icon.asset_id}
            blob = json.dumps(ids, sort_keys=True).encode()
            pack_hash = hashlib.sha256(blob + brief.encode()).hexdigest()
            pack = AssetPack(
                pack_id=f"pack_{pack_hash[:12]}",
                brief=brief,
                asset_ids=ids,
                content_hash=pack_hash,
                stage="GENERATED",
            )
            self.packs[pack.pack_id] = pack
            return pack

    def evolve_pack(self, brief: str, *, width: int = 128, height: int = 128) -> dict[str, Any]:
        pack = self.generate_pack(brief, width=width, height=height)
        applied: dict[str, Any] = {}
        for kind, aid in pack.asset_ids.items():
            self.validate(aid)
            a = self.assets[aid]
            if a.stage == AssetStage.REJECTED:
                pack.stage = "REJECTED"
                return {"ok": False, "pack": pack.as_dict(), "failed": a.as_dict()}
            self.stage(aid)
            self.apply(aid)
            applied[kind] = a.as_dict()
        pack.stage = "APPLIED"
        pack.research_tier = False
        self.appearance.pack_id = pack.pack_id
        self.store.put(
            kind="pack",
            body=json.dumps(pack.as_dict(), indent=2, sort_keys=True),
            backend="procedural_v1.7.1",
            stage="APPLIED",
            artifact_id=pack.pack_id,
            metadata={"brief": brief[:500], "content_hash": pack.content_hash},
            suffix=".json",
        )
        return {
            "ok": True,
            "pack": pack.as_dict(),
            "assets": applied,
            "appearance": self.appearance.as_dict(),
        }

    def evolve_looks(
        self, brief: str, *, kind: AssetKind = "avatar", width: int = 128, height: int = 128
    ) -> dict[str, Any]:
        a = self.generate(brief, kind=kind, width=width, height=height)
        self.validate(a.asset_id)
        if a.stage == AssetStage.REJECTED:
            return {"ok": False, "asset": a.as_dict()}
        self.stage(a.asset_id)
        profile = self.apply(a.asset_id)
        return {
            "ok": True,
            "asset": a.as_dict(),
            "appearance": profile.as_dict(),
            "preview_bytes": list(a.preview_bytes[:64]),  # small sample for Desktop
        }

    def preview_for_desktop(self, asset_id: str) -> dict[str, Any]:
        a = self._get(asset_id)
        return {
            "asset_id": a.asset_id,
            "kind": a.kind,
            "format": a.format,
            "content_hash": a.content_hash,
            "preview_text": a.body[:800],
            "preview_bytes_len": len(a.preview_bytes),
            "stage": a.stage.value,
        }

    def _get(self, asset_id: str) -> GeneratedAsset:
        if asset_id not in self.assets:
            raise KeyError(f"unknown asset_id={asset_id}")
        return self.assets[asset_id]

    def list_assets(self) -> list[dict[str, Any]]:
        return [a.as_dict() for a in self.assets.values()]

    def list_packs(self) -> list[dict[str, Any]]:
        return [p.as_dict() for p in self.packs.values()]
