"""v1.0-C — Full RL-DCA loop, ISE promote/revoke, live NAS."""
from __future__ import annotations

import pytest

from organism_sdk.interoceptive import HealthVector, viability_f
from organism_sdk.learned_ise import LearnedISE
from organism_sdk.metamodel import MetamodelTracker, SynthesisStage


def test_rldca_online_training_loop_improves():
    ise = LearnedISE()
    samples = []
    for i in range(30):
        h = HealthVector(thermal=0.4 + 0.01 * (i % 10), energy=0.7)
        samples.append((h, min(1.0, viability_f(h) + 0.2)))
    out = ise.train_online_loop(samples, epochs=4, lr=0.15)
    assert out["epochs"] == 4
    assert out["control_path_active"] is False
    assert out["final_mean_abs_err"] <= out["mean_abs_err_per_epoch"][0] + 1e-9
    assert ise.weights.updates >= 30


def test_promote_success_then_revoke_blocks_control():
    ise = LearnedISE()
    h = HealthVector(thermal=0.85)
    for _ in range(8):
        ise.shadow_compare(h)
    ise.record_shadow_validate(pass_rate=0.99, ece_ok=True)
    assert ise.promote() is True
    assert ise.control_path_active
    st = ise.estimate(h, for_control=True)
    assert "learned" in st.model_version
    rec = ise.revoke(reason="drift_detected")
    assert rec["revoked"] is True
    assert rec["was_active"] is True
    assert not ise.control_path_active
    with pytest.raises(PermissionError):
        ise.estimate(h, for_control=True)


def test_live_nas_searches_and_shadow_validates_winners():
    t = MetamodelTracker(enabled=True, exploration_mode=True)
    base = {
        "module_id": "nas_live",
        "name": "nas_live",
        "input_modality": "DENSE_VECTOR",
        "output_form": "FEATURE_VECTOR",
        "safety_declared": True,
        "may_actuate_until_promoted": False,
        "reliability_tier": "T3_LEARNED_UNCALIBRATED",
    }
    winners = t.nas_search(
        base,
        space={"readout_dim": [4, 8], "scale_hint": [1.0], "depth": [1, 2]},
        top_k=1,
    )
    assert winners, "expected at least one shadow-validated NAS winner"
    assert winners[0].stage == SynthesisStage.SHADOW_VALIDATED
    assert not winners[0].may_actuate
    t.promote_nas_winner(winners[0].organ_id)
    assert winners[0].stage == SynthesisStage.PROMOTED
    assert winners[0].may_actuate
    assert t.can_register_deliberation(winners[0].organ_id)
