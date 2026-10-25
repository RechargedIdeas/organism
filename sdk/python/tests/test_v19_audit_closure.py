"""v1.9 audit closure — hosted LLM refuse, sandbox isolate, image backend, templates."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from organism_sdk.generative import (
    ArtifactStore,
    AssetPipeline,
    HostedImageBackend,
    HostedImageRefused,
    HostedLLMBackend,
    HostedLLMRefused,
    ProceduralImageBackend,
    SafeSandbox,
    list_templates,
    resolve_backend,
    resolve_image_backend,
)


def test_templates_expanded():
    names = list_templates()
    assert len(names) >= 10
    for n in ("normalizer", "ranker", "smoother", "gate", "scorer"):
        assert n in names


def test_hosted_llm_never_default_on():
    os.environ.pop("ORGANISM_LLM_ENABLED", None)
    b = HostedLLMBackend()
    with pytest.raises(HostedLLMRefused):
        b.draft("write a scorer")
    assert resolve_backend("template").name == "template"


def test_hosted_llm_requires_url_key(monkeypatch):
    monkeypatch.setenv("ORGANISM_LLM_ENABLED", "1")
    monkeypatch.delenv("ORGANISM_LLM_URL", raising=False)
    monkeypatch.delenv("ORGANISM_LLM_API_KEY", raising=False)
    b = HostedLLMBackend()
    with pytest.raises(HostedLLMRefused):
        b.draft("x")


def test_sandbox_process_isolation_ok():
    sb = SafeSandbox(isolate=True, timeout_s=2.0, max_rss_mb=256)
    r = sb.run("def main(**k):\n    return {'ok': True, 'score': 3}\n")
    assert r.ok
    assert r.isolated is True
    assert r.value["score"] == 3


def test_sandbox_timeout():
    sb = SafeSandbox(isolate=True, timeout_s=0.2, max_rss_mb=256)
    # busy loop without imports — may timeout
    src = "def main(**k):\n    n = 0\n    while n < 10**9:\n        n = n + 1\n    return {'ok': True}\n"
    r = sb.run(src)
    assert r.ok is False
    assert "Timeout" in (r.error or "") or "Sandbox" in (r.error or "")


def test_sandbox_ast_still_blocks_import():
    sb = SafeSandbox(isolate=True, timeout_s=2.0)
    r = sb.run("import os\ndef main(**k):\n    return os.getcwd()\n")
    assert r.ok is False
    assert "SandboxRefused" in (r.error or "")


def test_image_backend_procedural(tmp_path: Path):
    art = ArtifactStore(tmp_path / "art")
    pipe = AssetPipeline(art, image_backend=ProceduralImageBackend())
    asset = pipe.generate("ocean organism theme", kind="theme")
    assert asset.format == "json"
    assert "procedural_v1.9" in asset.body
    skin = pipe.generate("banner look", kind="skin")
    assert "<svg" in skin.body


def test_hosted_image_refuses_until_enabled():
    b = HostedImageBackend()
    with pytest.raises(HostedImageRefused):
        b.render("x", kind="avatar", width=64, height=64, palette={"primary": "#111", "accent": "#222", "background": "#000", "foreground": "#fff"})
    assert resolve_image_backend("procedural").name.startswith("procedural")


def test_promote_product_limit_documented():
    # Structural: GeneratedSkillModule / hot-register path keeps may_actuate False
    from organism_sdk.generative.runtime import GeneratedSkillModule

    mod = GeneratedSkillModule(module_id="gen_test", source="def main(**k):\n    return {'ok': True}\n", intent="test")
    c = mod.declare_contract()
    assert c.safety.may_actuate is False
