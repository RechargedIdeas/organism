"""v0.3-M2 — Metamodel reproductive synthesizer path."""
from __future__ import annotations

import pytest

from organism_sdk.metamodel import MetamodelDisabled, MetamodelTracker, SynthesisStage


def _spec(**kw):
    base = {
        "module_id": "adapter_alpha",
        "name": "adapter_alpha",
        "input_modality": "DENSE_VECTOR",
        "output_form": "FEATURE_VECTOR",
        "safety_declared": True,
        "may_actuate_until_promoted": False,
        "reliability_tier": "T3_LEARNED_UNCALIBRATED",
        "readout_dim": 4,
    }
    base.update(kw)
    return base


def test_disabled_still_raises_metamodel_disabled():
    t = MetamodelTracker(enabled=False)
    assert not t.reproductive_path_enabled()
    with pytest.raises(MetamodelDisabled):
        t.synthesize(_spec())
    assert t.attempts[-1]["reason"] == "E.8_metamodel_reproductive_disabled"


def test_synthesize_sandbox_shadow_promote():
    t = MetamodelTracker(enabled=True, exploration_mode=True)
    organ = t.synthesize(_spec())
    assert organ.stage == SynthesisStage.SYNTHESIZED
    assert not organ.may_actuate
    assert not t.can_register_deliberation(organ.organ_id)

    t.sandbox(organ.organ_id)
    assert organ.stage == SynthesisStage.SANDBOXED

    t.shadow_validate(organ.organ_id, pass_rate=0.95)
    assert organ.stage == SynthesisStage.SHADOW_VALIDATED
    assert not organ.may_actuate

    t.promote(organ.organ_id)
    assert organ.stage == SynthesisStage.PROMOTED
    assert organ.may_actuate
    assert t.can_register_deliberation(organ.organ_id)


def test_shadow_reject_blocks_actuation_and_deliberation():
    t = MetamodelTracker(enabled=True)
    organ = t.synthesize(_spec(module_id="adapter_bad"))
    t.sandbox(organ.organ_id)
    t.shadow_validate(organ.organ_id, pass_rate=0.2)
    assert organ.stage == SynthesisStage.REJECTED
    assert not organ.may_actuate
    with pytest.raises(PermissionError):
        t.promote(organ.organ_id)
    assert not t.can_register_deliberation(organ.organ_id)


def test_non_exploration_blocks_synthesis():
    t = MetamodelTracker(enabled=True, exploration_mode=False)
    with pytest.raises(MetamodelDisabled):
        t.synthesize(_spec())


def test_four_part_contract_required():
    t = MetamodelTracker(enabled=True)
    with pytest.raises(ValueError, match="four-part"):
        t.synthesize({"module_id": "x"})  # missing perception/emission
