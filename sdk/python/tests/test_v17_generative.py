"""v1.7 / v1.7.1 — Organism generative code/asset/skill evolution."""
from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path

import pytest

from organism_sdk.generative import (
    ArtifactStore,
    AssetPipeline,
    CodePipeline,
    DraftReplayLog,
    GeneratorBackend,
    IntegrityError,
    LLMStubBackend,
    OrganismStore,
    PromoteRefused,
    SafeSandbox,
    SkillRegistry,
    TemplateDraftBackend,
    contrast_ratio,
    list_templates,
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


def test_sandbox_refuses_eval_and_getattr():
    sb = SafeSandbox()
    assert not sb.run("def main():\n    return eval('1')\n").ok
    assert not sb.run("def main():\n    return getattr(dict, '__class__')\n").ok


def test_code_pipeline_promote_gate(art: ArtifactStore):
    pipe = CodePipeline(art)
    b = pipe.evolve("Organism adder skill", spec={"skill_name": "adder", "may_actuate": False})
    assert b.stage.value == "SHADOW_SCORED"
    assert b.gate.ready()
    assert b.may_control is False
    assert b.shadow_metrics.get("total", 0) >= 0.9
    with pytest.raises(PromoteRefused):
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


def test_template_library_richer(art: ArtifactStore):
    assert "navigator" in list_templates()
    assert "classifier" in list_templates()
    pipe = CodePipeline(art)
    b = pipe.evolve("Organism navigator route", spec={"skill_name": "navigator", "may_actuate": False})
    assert "template=navigator" in b.source or "navigator" in b.source
    assert b.stage.value == "SHADOW_SCORED"


def test_generator_backend_protocol(art: ArtifactStore):
    class Custom:
        name = "custom"

        def draft(self, intent: str, *, spec=None) -> str:
            return "def main(x=0, **kwargs):\n    return {'ok': True, 'score': 1.0, 'skill': 'c'}\n"

    assert isinstance(Custom(), GeneratorBackend)
    pipe = CodePipeline(art, backend=Custom())  # type: ignore[arg-type]
    b = pipe.evolve("custom", auto_promote=True)
    assert b.may_control


def test_replayable_drafts(art: ArtifactStore, tmp_path: Path):
    log = DraftReplayLog(tmp_path / "replay.json")
    pipe = CodePipeline(art, replay_log=log)
    b = pipe.start("replay me", spec={"skill_name": "adder"})
    assert b.replay_id
    again = pipe.replay_draft(b.replay_id)
    assert again.source == b.source
    assert again.intent == b.intent


def test_rollback_last_promote(art: ArtifactStore):
    pipe = CodePipeline(art)
    a = pipe.evolve("first", auto_promote=True)
    b = pipe.evolve("second", auto_promote=True)
    assert pipe.last_promoted_id == b.bundle_id
    rb = pipe.rollback_last_promote()
    assert rb.bundle_id == b.bundle_id
    assert rb.stage.value == "ROLLBACK"
    assert rb.may_control is False
    assert pipe.last_promoted_id == a.bundle_id


def test_stage_progress_summary(art: ArtifactStore):
    pipe = CodePipeline(art)
    b = pipe.evolve("progress", auto_promote=False)
    prog = pipe.stage_progress_summary(b.bundle_id)
    assert "SHADOW_SCORED" in prog["progress"]
    assert prog["stage"] == "SHADOW_SCORED"


def test_concurrent_artifact_store(tmp_path: Path):
    store = ArtifactStore(tmp_path / "art")

    def writer(i: int):
        return store.put(
            kind="code",
            body=f"def main():\n    return {i}\n",
            backend="t",
            stage="DRAFT",
            artifact_id=f"c_{i}",
            suffix=".py",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        recs = list(ex.map(writer, range(20)))
    assert len(recs) == 20
    assert len(store.list_ids(kind="code")) == 20
    v = store.verify(recs[0].artifact_id)
    assert v["ok"]


def test_artifact_integrity_mismatch(art: ArtifactStore, tmp_path: Path):
    rec = art.put(kind="code", body="def main():\n    return 1\n", backend="t", stage="DRAFT", suffix=".py")
    path = Path(rec.metadata["path"])
    path.write_text("tampered", encoding="utf-8")
    with pytest.raises(IntegrityError):
        art.read_body(rec)


def test_asset_pipeline_looks(art: ArtifactStore, tmp_path: Path):
    ap = AssetPipeline(art, assets_root=tmp_path / "assets")
    r = ap.evolve_looks("teal Organism", kind="avatar")
    assert r["ok"]
    assert r["appearance"]["revision"] == 1
    assert r["asset"]["content_hash"]
    assert r["asset"]["preview_b64_len"] > 0
    theme = ap.evolve_looks("night theme", kind="theme")
    assert theme["ok"]
    assert theme["appearance"]["palette"]
    assert theme["asset"]["contrast_ok"] is True


def test_asset_pack_multi(art: ArtifactStore, tmp_path: Path):
    ap = AssetPipeline(art, assets_root=tmp_path / "assets")
    r = ap.evolve_pack("coral Organism pack")
    assert r["ok"]
    assert set(r["pack"]["asset_ids"]) == {"avatar", "theme", "icon"}
    assert r["appearance"]["pack_id"]
    assert r["appearance"]["revision"] >= 3


def test_asset_rejects_forbidden_brief(art: ArtifactStore, tmp_path: Path):
    ap = AssetPipeline(art, assets_root=tmp_path / "assets")
    a = ap.generate("weaponize something", kind="icon")
    ap.validate(a.asset_id)
    assert a.stage.value == "REJECTED"


def test_asset_rejects_oversized(art: ArtifactStore, tmp_path: Path):
    ap = AssetPipeline(art, assets_root=tmp_path / "assets")
    huge = "<svg>" + ("x" * 300_000) + "</svg>"
    a = ap.generate("big", kind="avatar", body_override=huge)
    ap.validate(a.asset_id)
    assert a.stage.value == "REJECTED"
    assert any("size" in e for e in a.validation_errors)


def test_asset_rejects_malformed_svg(art: ArtifactStore, tmp_path: Path):
    ap = AssetPipeline(art, assets_root=tmp_path / "assets")
    a = ap.generate("bad", kind="icon", body_override="<div>not svg</div>")
    ap.validate(a.asset_id)
    assert a.stage.value == "REJECTED"


def test_theme_contrast_helper():
    assert contrast_ratio("#ffffff", "#000000") > 20


def test_skills_and_organism_store(art: ArtifactStore, tmp_path: Path):
    pipe = CodePipeline(art)
    skills = SkillRegistry(art)
    store = OrganismStore(tmp_path / "organisms")
    profile = store.ensure_default()
    skill, bundle = skills.generate_skill(
        "scout", intent="scout terrain", code_pipeline=pipe, auto_promote=True
    )
    assert skill.may_control is True
    assert skill.version == "0.1.0"
    store.sync_skills(profile.organism_id, skills.list_skills())
    store.add_code_revision(profile.organism_id, bundle.as_dict())
    store.log(profile.organism_id, "skill_promote", "promoted scout")
    got = store.get(profile.organism_id)
    assert got is not None
    assert len(got.skills) == 1
    assert len(got.evolution_log) >= 1
    assert "sophont" not in got.organism_id.lower()


def test_skill_dependency_dag(art: ArtifactStore):
    from organism_sdk.generative.skills import SkillDescriptor

    pipe = CodePipeline(art)
    skills = SkillRegistry(art)
    base, _ = skills.generate_skill("base", intent="base skill", code_pipeline=pipe, auto_promote=True)
    child, _ = skills.generate_skill(
        "child",
        intent="child skill",
        code_pipeline=pipe,
        auto_promote=True,
        depends_on=(base.skill_id,),
    )
    dag = skills.dependency_dag()
    assert any(e["from"] == base.skill_id and e["to"] == child.skill_id for e in dag["edges"])
    assert dag["layers"][0]  # base layer non-empty
    with pytest.raises(ValueError, match="cycle"):
        skills.register(
            SkillDescriptor(
                skill_id=base.skill_id,
                name="base",
                depends_on=(child.skill_id,),
            )
        )


def test_improve_from_trace(art: ArtifactStore, tmp_path: Path):
    pipe = CodePipeline(art)
    skills = SkillRegistry(art)
    store = OrganismStore(tmp_path / "organisms")
    profile = store.ensure_default()
    skill, _ = skills.generate_skill("traceable", intent="v1", code_pipeline=pipe, auto_promote=False)
    store.log(profile.organism_id, "skill_generate", "Generated traceable", payload={"skill_id": skill.skill_id})
    store.log(profile.organism_id, "note", "need better scoring")
    profile = store.get(profile.organism_id)
    assert profile is not None
    improved, bundle = skills.improve_from_trace(
        skill.skill_id,
        evolution_log=profile.evolution_log,
        code_pipeline=pipe,
        auto_promote=False,
    )
    assert "from_trace" in improved.tags
    assert improved.version != "0.1.0"
    assert bundle.stage.value in ("SHADOW_SCORED", "PROMOTED", "REJECTED")


def test_promote_skill_requires_shadow_threshold(art: ArtifactStore):
    pipe = CodePipeline(art, min_shadow=0.9)
    skills = SkillRegistry(art, min_shadow_for_promote=0.99)
    skill, bundle = skills.generate_skill(
        "strict", intent="strict gate", code_pipeline=pipe, auto_promote=False
    )
    # artificially lower skill shadow below registry threshold but keep bundle gate ready
    skill.shadow_score = 0.5
    skills.register(skill)
    # bundle may still promote via code pipeline; skill promote checks skill.shadow first then refreshes
    # Force live bundle score low
    bundle.shadow_score = 0.5
    bundle.gate.shadow_score = 0.5
    bundle.gate.shadow_validated = True
    bundle.gate.static_ok = True
    bundle.gate.contract_ok = True
    bundle.gate.sandbox_ok = True
    with pytest.raises(PromoteRefused):
        skills.promote_skill(skill.skill_id, code_pipeline=pipe)


def test_fuzz_unsafe_code_drafts_must_refuse(art: ArtifactStore):
    """Fuzz unsafe code drafts — every payload must be REJECTED or sandbox-fail."""
    pipe = CodePipeline(art)
    payloads = [
        "import os\ndef main():\n    return os.system('id')\n",
        "def main():\n    return eval('1+1')\n",
        "def main():\n    return __import__('os').system('x')\n",
        "import subprocess\ndef main():\n    subprocess.call(['echo','x'])\n",
        "def main():\n    open('/etc/passwd').read()\n",
        "may_actuate = True\ndef main():\n    return 1\n",
        "def main():\n    return getattr(__builtins__, 'eval')('1')\n",
        "async def main():\n    return 1\n",
        "class X:\n    pass\ndef main():\n    return X\n",
        "def main():\n    return (lambda: 1)()\n",
        "import socket\ndef main():\n    return 1\n",
        "def main():\n    exec('x=1')\n    return 1\n",
    ]

    class FuzzBackend(TemplateDraftBackend):
        def __init__(self, src: str):
            self._src = src
            self.name = "fuzz"

        def draft(self, intent, *, spec=None):
            return self._src

    for src in payloads:
        b = pipe.evolve("fuzz", backend=FuzzBackend(src), auto_promote=False)
        assert b.stage.value == "REJECTED", (
            f"expected REJECTED for {src!r}, got {b.stage} "
            f"errs={b.static_errors + b.contract_errors}"
        )
        assert b.may_control is False
        # Gate must not be ready after rejection (static/contract/sandbox failed).
        assert b.gate.ready() is False
        with pytest.raises(PromoteRefused):
            pipe.promote(b.bundle_id)
