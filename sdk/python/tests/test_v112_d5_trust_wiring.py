"""The trust store under the reference experts, the generative runtime and the stack (GAP_ANALYSIS D5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from organism_sdk.deploy.config import default_cpu_only_config
from organism_sdk.deploy.stack import build_minimal_stack
from organism_sdk.errors import RegistrationRejected
from organism_sdk.generative import ArtifactStore, CodePipeline, EvolutionRuntime, SkillRegistry
from organism_sdk.moa.experts import register_experts
from organism_sdk.moa.reference import reference_expert_ids, reference_experts
from organism_sdk.registry import RegistryClient
from organism_sdk.signing import TrustStore
from organism_sdk.trace import TraceEmitter


def _empty_trust_file(path: Path) -> Path:
    path.write_text(json.dumps({"authors": [], "approvers": []}), encoding="utf-8")
    return path


def test_reference_experts_register_only_with_their_ids_listed_as_built_in() -> None:
    with pytest.raises(RegistrationRejected):
        register_experts(RegistryClient(trust_store=TrustStore()), reference_experts())
    listed = RegistryClient(trust_store=TrustStore(), builtin_ids=reference_expert_ids())
    assert len(register_experts(listed, reference_experts())) == 2


def test_reference_expert_ids_are_the_expert_module_ids() -> None:
    assert reference_expert_ids() == {"moa.intent_classifier", "moa.extractor"}


def test_build_minimal_stack_adds_the_callers_builtin_ids(tmp_path: Path) -> None:
    cfg = default_cpu_only_config()
    cfg.stack.trust_store = str(_empty_trust_file(tmp_path / "trust.json"))
    expert = reference_experts()[0]
    with pytest.raises(RegistrationRejected):
        register_experts(build_minimal_stack(cfg).registry, [expert])
    listed = build_minimal_stack(cfg, builtin_ids=reference_expert_ids()).registry
    assert len(register_experts(listed, [expert])) == 1


def test_generative_output_is_refused_under_a_trust_store(tmp_path: Path) -> None:
    art = ArtifactStore(tmp_path / "artifacts")
    pipe = CodePipeline(art)
    skills = SkillRegistry(art)
    _skill, bundle = skills.generate_skill(
        "runtime_scout", intent="scout", code_pipeline=pipe, auto_promote=False
    )
    promoted = pipe.promote(bundle.bundle_id)
    reg = RegistryClient(trust_store=TrustStore())
    rt = EvolutionRuntime(registry=reg, trace=TraceEmitter(), modules={}, pulse_on_promote=False)
    assert rt.hot_register_promoted(promoted) is None
    assert reg.list_module_ids() == []
    assert rt.catalog_entries() == []
