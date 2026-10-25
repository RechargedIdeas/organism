"""v1.7 — Organism generative code/asset/skill evolution."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from organism_sdk.generative import (
    ArtifactStore,
    AssetPipeline,
    CodePipeline,
    LLMStubBackend,
    OrganismStore,
    PromoteRefused,
    SafeSandbox,
    SkillRegistry,
    TemplateDraftBackend,
)


@pytest.fixture()
def art(tmp_path: Path):
    return ArtifactStore(tmp_path / "artifacts")


def test_sandbox_allows_pure_main():
    sb = SafeSandbox()
    src = "def main(x=1):\n    return x * 2\n"
    r = sb.run(src, args={"x": 3})
    assert r.ok and r.value == 6


def test_sandbox_refuses_import_os():
    sb = SafeSandbox()
    r = sb.run("import os\ndef main():\n    return os.getcwd()\n")
    assert not r.ok and "SandboxRefused" in (r.error or "")


def test_sandbox_refuses_subprocess_name():
    sb = SafeSandbox()
    r = sb.run("def main():\n    return subprocess\n")
    assert not r.ok


def test_code_pipeline_promote_gate(art: ArtifactStore):
    pipe = CodePipeline(art)
    b = pipe.evolve("Organism adder skill", spec={"skill_name": "adder", "may_actuate": False})
    assert b.stage.value == "SHADOW_SCORED"
    assert b.gate.ready()
    assert b.may_control is False
    with pytest.raises(PromoteRefused):
        # wipe readiness
        b.gate.shadow_validated = False
        pipe.promote(b.bundle_id)
    b.gate.shadow_validated = True
    b.gate.shadow_score = 0.95
    promoted = pipe.promote(b.bundle_id)
    assert promoted.may_control is True
    assert promoted.stage.value == "PROMOTED"
    dem = pipe.demote(b.bundle_id)
    assert dem.may_control is False


def test_code_pipeline_rejects_shellish(art: ArtifactStore):
    pipe = CodePipeline(art)
    # monkeypatch backend
    class Bad(TemplateDraftBackend):
        def draft(self, intent, *, spec=None):
            return "import os\ndef main():\n    return os.system('echo x')\n"

    b = pipe.evolve("hack", backend=Bad())
    assert b.stage.value == "REJECTED"
    assert b.static_errors


def test_code_pipeline_rejects_may_actuate_true(art: ArtifactStore):
    pipe = CodePipeline(art)

    class Bad(TemplateDraftBackend):
        def draft(self, intent, *, spec=None):
            return "may_actuate = True\ndef main():\n    return 1\n"

    b = pipe.evolve("bad", spec={"may_actuate": False}, backend=Bad())
    assert b.stage.value == "REJECTED"
    assert any("may_actuate" in e for e in b.contract_errors)


def test_llm_stub_backend_deterministic(art: ArtifactStore):
    pipe = CodePipeline(art)
    a = pipe.evolve("same", backend=LLMStubBackend(), auto_promote=True)
    b = pipe.evolve("same", backend=LLMStubBackend(), auto_promote=True)
    assert a.source == b.source
    assert a.may_control and b.may_control


def test_asset_pipeline_looks(art: ArtifactStore, tmp_path: Path):
    ap = AssetPipeline(art, assets_root=tmp_path / "assets")
    r = ap.evolve_looks("teal Organism", kind="avatar")
    assert r["ok"]
    assert r["appearance"]["revision"] == 1
    assert (tmp_path / "assets").exists()
    theme = ap.evolve_looks("night theme", kind="theme")
    assert theme["ok"]
    assert theme["appearance"]["palette"]


def test_asset_rejects_forbidden_brief(art: ArtifactStore, tmp_path: Path):
    ap = AssetPipeline(art, assets_root=tmp_path / "assets")
    a = ap.generate("weaponize something", kind="icon")
    ap.validate(a.asset_id)
    assert a.stage.value == "REJECTED"


def test_skills_and_organism_store(art: ArtifactStore, tmp_path: Path):
    pipe = CodePipeline(art)
    skills = SkillRegistry(art)
    store = OrganismStore(tmp_path / "organisms")
    profile = store.ensure_default()
    skill, bundle = skills.generate_skill(
        "scout", intent="scout terrain", code_pipeline=pipe, auto_promote=True
    )
    assert skill.may_control is True
    store.sync_skills(profile.organism_id, skills.list_skills())
    store.add_code_revision(profile.organism_id, bundle.as_dict())
    store.log(profile.organism_id, "skill_promote", "promoted scout")
    got = store.get(profile.organism_id)
    assert got is not None
    assert len(got.skills) == 1
    assert len(got.evolution_log) >= 1
    assert "sophont" not in got.organism_id.lower()
