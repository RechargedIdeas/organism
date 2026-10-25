"""v1.8 Organism surfaces — theme apply, rollback deregister, multi-Organism, bundles."""
from __future__ import annotations

from pathlib import Path

import pytest

from organism_sdk.deploy.config import default_cpu_only_config
from organism_sdk.deploy.stack import build_minimal_stack
from organism_sdk.generative import (
    ArtifactStore,
    AssetPipeline,
    CodePipeline,
    EvolutionRuntime,
    OrganismStore,
    SkillRegistry,
    export_organism_bundle,
    import_organism_bundle,
    normalize_palette,
    shell_accent_qss,
    theme_apply_payload,
)
from organism_sdk.generative.skills import SkillDescriptor
from organism_sdk.trace import V02TraceSink


@pytest.fixture
def art(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "art")


def test_theme_qss_and_payload():
    p = normalize_palette({"primary": "#112233", "accent": "#aabbcc"})
    assert p["primary"] == "#112233"
    assert p["foreground"]  # default filled
    qss = shell_accent_qss(p)
    assert "112233" in qss
    assert "nav_list" in qss
    payload = theme_apply_payload({"theme_id": "t1", "palette": p, "revision": 2})
    assert payload["ok"] and payload["applied"]
    assert payload["may_actuate"] is False
    assert payload["cpu_everywhere"] is True
    assert "qss" in payload


def test_multi_organism_store_switch(tmp_path: Path):
    store = OrganismStore(tmp_path / "orgs")
    a = store.ensure_default()
    assert store.active_id() == a.organism_id
    b = store.create(display_name="Twin Organism", make_active=True)
    assert store.active_id() == b.organism_id
    store.switch(a.organism_id)
    assert store.active_id() == a.organism_id
    summaries = store.list_summaries()
    assert len(summaries) >= 2
    assert sum(1 for s in summaries if s["active"]) == 1
    # persistence
    store2 = OrganismStore(tmp_path / "orgs")
    assert store2.active_id() == a.organism_id


def test_rollback_deregisters_generated_module(art: ArtifactStore, tmp_path: Path):
    stack = build_minimal_stack(default_cpu_only_config())
    stack.trace.attach_v02_sink(V02TraceSink())
    runtime = EvolutionRuntime(
        registry=stack.registry,
        trace=stack.trace,
        modules=stack.modules,
        pulse_on_promote=False,
    )
    pipe = CodePipeline(art)
    bundle = pipe.evolve("deregister target", auto_promote=True)
    assert bundle.may_control
    hot = runtime.after_promote(bundle, organism_id="organism_primary")
    mid = hot["hot_register"]["module_id"]
    assert mid in stack.registry.list_module_ids()
    rb = pipe.rollback_last_promote(reason="test_rollback")
    assert rb.bundle_id == bundle.bundle_id
    result = runtime.after_rollback(rb, organism_id="organism_primary", reason="test_rollback")
    assert result["deregister"]["deregistered"] is True
    assert result["deregister"]["module_id"] == mid
    assert mid not in stack.registry.list_module_ids()


def test_export_import_bundle_roundtrip(art: ArtifactStore, tmp_path: Path):
    store = OrganismStore(tmp_path / "orgs")
    profile = store.ensure_default()
    skills = SkillRegistry(art)
    skills.register(
        SkillDescriptor(
            skill_id="sk_nav",
            name="navigator",
            description="nav skill",
            research_tier=True,
            may_control=False,
        )
    )
    store.sync_skills(profile.organism_id, skills.list_skills())
    assets = AssetPipeline(art, assets_root=tmp_path / "assets")
    looks = assets.evolve_looks("teal theme Organism", kind="theme")
    assert looks["ok"]
    store.sync_appearance(profile.organism_id, assets.appearance)
    dest = tmp_path / "bundle.zip"
    exported = export_organism_bundle(
        profile=store.get(profile.organism_id),
        skills=skills.list_skills(),
        appearance=assets.appearance,
        asset_pipeline=assets,
        dest=dest,
    )
    assert exported["ok"]
    assert dest.is_file()
    assert exported["manifest"]["format"] == "organism_bundle_v1"

    # Fresh store / registries for import
    store2 = OrganismStore(tmp_path / "orgs2")
    skills2 = SkillRegistry(art)
    assets2 = AssetPipeline(art, assets_root=tmp_path / "assets2")
    imported = import_organism_bundle(
        path=dest,
        organism_store=store2,
        skill_registry=skills2,
        asset_pipeline=assets2,
        switch_active=True,
    )
    assert imported["ok"]
    assert imported["organism_id"] == profile.organism_id
    assert "sk_nav" in imported["skills_imported"]
    assert store2.active_id() == profile.organism_id
    # Imported skills stay RESEARCH / no control
    sk = skills2.get("sk_nav")
    assert sk is not None
    assert sk.may_control is False
    assert sk.research_tier is True
    assert assets2.appearance.palette
