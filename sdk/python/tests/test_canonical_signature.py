"""Canonical JSON writer (C3) and Ed25519 verification (A9) against the conformance vectors."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from organism_sdk.canonical import CanonicalError, canonical_bytes, canonical_text
from organism_sdk.signing import generate_seed, public_key_for, sign, verify

VECTORS = Path(__file__).resolve().parents[3] / "conformance" / "vectors"


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((VECTORS / f"{name}.json").read_text(encoding="utf-8"))
    return data


@pytest.mark.parametrize("case", _load("canonical")["cases"], ids=lambda c: c["name"])
def test_canonical_vectors(case: dict[str, Any]) -> None:
    value = json.loads(case["input"])
    if "error" in case:
        with pytest.raises(CanonicalError) as err:
            canonical_text(value)
        assert err.value.code == case["error"]
    else:
        assert canonical_text(value) == case["canonical"]
        assert canonical_bytes(value).hex() == case["hex"]


def test_canonical_rules() -> None:
    assert canonical_text({"b": [True, None], "a": (1, 2)}) == '{"a":[1,2],"b":[true,null]}'
    assert canonical_text(True) == "true"  # bool is not written as 1
    assert canonical_text("é").encode("utf-8") == b'"\xc3\xa9"'
    assert canonical_bytes("é") == b'"\xc3\xa9"'
    assert canonical_text(2**53 - 1) == "9007199254740991"


@pytest.mark.parametrize(
    ("value", "code"),
    [({1: "a"}, "non_string_key"), (object(), "unsupported_type"), (b"x", "unsupported_type"),
     (float("nan"), "non_finite_number"), (float("-inf"), "non_finite_number"), (2.0, "float_not_allowed"),
     (2**53, "integer_out_of_range")],
)
def test_canonical_rejects(value: object, code: str) -> None:
    with pytest.raises(CanonicalError) as err:
        canonical_text(value)
    assert err.value.code == code


@pytest.mark.parametrize("case", _load("signature")["cases"], ids=lambda c: c["name"])
def test_signature_vectors(case: dict[str, Any]) -> None:
    got = verify(bytes.fromhex(case["public_key"]), bytes.fromhex(case["signature"]), bytes.fromhex(case["message"]))
    assert got is case["valid"]


def test_signature_round_trip() -> None:
    seed = generate_seed()
    sig = sign(seed, b"payload")
    assert verify(public_key_for(seed), sig, b"payload")
    assert not verify(public_key_for(seed), sig, b"payloae")
