"""v1.13 NLP-CLI adapter: the model digest is computed from the file and must match its sidecar."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from nlp_cli import RouterError, model_digest, router_contract

MODEL_BYTES = b'{"weights": [0.1, 0.2]}\n'


def _model_with_sidecar(tmp_path: Path, data: bytes = MODEL_BYTES) -> Path:
    model = tmp_path / "t1.json"
    model.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    model.with_name("t1.json.sha256").write_text(f"{digest}  t1.json\n", encoding="utf-8")
    return model


def test_the_digest_is_the_hash_of_the_file(tmp_path: Path) -> None:
    model = _model_with_sidecar(tmp_path)
    assert model_digest(model) == hashlib.sha256(MODEL_BYTES).digest()


def test_a_missing_sidecar_is_refused(tmp_path: Path) -> None:
    model = tmp_path / "t1.json"
    model.write_bytes(MODEL_BYTES)
    with pytest.raises(RouterError, match="no digest sidecar"):
        model_digest(model)


def test_a_sidecar_that_does_not_match_the_file_is_refused(tmp_path: Path) -> None:
    model = _model_with_sidecar(tmp_path)
    model.write_bytes(b"edited after training")
    with pytest.raises(RouterError, match="does not match"):
        model_digest(model)


@pytest.mark.parametrize("content", ["", "abc  t1.json\n", "z" * 64 + "  t1.json\n"])
def test_a_sidecar_that_holds_no_digest_is_refused(tmp_path: Path, content: str) -> None:
    model = tmp_path / "t1.json"
    model.write_bytes(MODEL_BYTES)
    model.with_name("t1.json.sha256").write_text(content, encoding="utf-8")
    with pytest.raises(RouterError):
        model_digest(model)


def test_the_router_contract_carries_the_file_digest(tmp_path: Path) -> None:
    model = _model_with_sidecar(tmp_path)
    contract = router_contract(version="0.2.0", artifact_digest=model_digest(model))
    assert contract.identity.artifact_digest == hashlib.sha256(MODEL_BYTES).digest()


_REAL_MODEL = os.environ.get("NLPCLI_MODEL")


@pytest.mark.skipif(not _REAL_MODEL, reason="set NLPCLI_MODEL to the model file to run")
def test_the_real_model_matches_its_sidecar() -> None:
    model = Path(_REAL_MODEL or "")
    claimed = model.with_name(model.name + ".sha256").read_text(encoding="utf-8").split()[0]
    assert model_digest(model).hex() == claimed
