"""v1.13 model-quality record and gate (gap H3)."""

from __future__ import annotations

import pytest
from organism_sdk.quality import QualityRecord, QualityRequirement, quality_gate, to_ppm

MODEL = b"\x01" * 32
OTHER_MODEL = b"\x02" * 32
SET = b"\x03" * 32


def _record(**overrides: object) -> QualityRecord:
    base: dict[str, object] = {
        "model_digest": MODEL,
        "eval_set_digest": SET,
        "eval_set_name": "heldout.v5",
        "samples": 110,
        "metrics": {"accuracy": to_ppm(0.8), "intent": to_ppm(0.9)},
        "clean": True,
    }
    base.update(overrides)
    return QualityRecord(**base)  # type: ignore[arg-type]


def test_to_ppm_rounds_and_refuses_bad_values() -> None:
    assert to_ppm(0.0) == 0
    assert to_ppm(1.0) == 1_000_000
    assert to_ppm(0.6553) == 655_300
    for bad in (-0.1, 1.1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            to_ppm(bad)


def test_the_digest_is_stable_and_changes_with_any_field() -> None:
    assert _record().digest() == _record().digest()
    assert _record().digest() != _record(samples=111).digest()
    assert _record().digest() != _record(clean=False).digest()
    assert _record().digest() != _record(metrics={"accuracy": 1}).digest()


def test_a_good_record_passes_the_gate() -> None:
    issues = quality_gate(
        _record(),
        [QualityRequirement("accuracy", to_ppm(0.7))],
        expected_model_digest=MODEL,
    )
    assert issues == []


def test_a_metric_below_its_minimum_stops_promotion() -> None:
    issues = quality_gate(_record(), [QualityRequirement("accuracy", to_ppm(0.85))])
    assert [i.code for i in issues] == ["quality_below_minimum"]


def test_a_missing_metric_stops_promotion() -> None:
    issues = quality_gate(_record(), [QualityRequirement("macro_f1", 1)])
    assert [i.code for i in issues] == ["quality_metric_missing"]


def test_a_record_for_another_model_is_refused() -> None:
    issues = quality_gate(_record(), [], expected_model_digest=OTHER_MODEL)
    assert [i.code for i in issues] == ["quality_model_mismatch"]


def test_too_few_samples_and_a_used_set_are_refused() -> None:
    issues = quality_gate(_record(samples=20, clean=False), [])
    assert sorted(i.code for i in issues) == ["quality_not_clean", "quality_samples_insufficient"]


def test_an_unclean_set_is_allowed_only_when_the_requirement_says_so() -> None:
    assert quality_gate(_record(clean=False), [], require_clean=False) == []


def test_a_record_without_its_digests_is_refused() -> None:
    issues = quality_gate(_record(model_digest=b"", eval_set_digest=b""), [])
    assert [i.code for i in issues] == ["quality_digest_missing"]
