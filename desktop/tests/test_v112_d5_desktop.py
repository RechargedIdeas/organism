"""The desktop under a trust store: its own modules register, and generative output does not (GAP_ANALYSIS D5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from bio_digital.mycelium import MODULE_ID as MYCELIUM_ID
from bio_digital.slime_mold import MODULE_ID as SLIME_MOLD_ID
from organism_desktop.catalog import BIO_MODULE_IDS, CATALOG, DESKTOP_BUILTIN_IDS
from organism_desktop.service import DesktopService
from organism_sdk.deploy.config import default_cpu_only_config


@pytest.fixture
def trusted(tmp_path: Path) -> DesktopService:
    trust = tmp_path / "trust.json"
    trust.write_text(json.dumps({"authors": [], "approvers": []}), encoding="utf-8")
    cfg = default_cpu_only_config()
    cfg.stack.trust_store = str(trust)
    return DesktopService.create(cfg, data_root=tmp_path / "organism_data")


def test_the_bio_ids_are_the_ids_of_the_bio_modules() -> None:
    assert BIO_MODULE_IDS == {SLIME_MOLD_ID, MYCELIUM_ID}


def test_desktop_builtin_ids_are_its_catalog_and_bio_modules_and_no_generative_output() -> None:
    assert DESKTOP_BUILTIN_IDS == {e.module_id for e in CATALOG} | BIO_MODULE_IDS
    assert not any(module_id.startswith("gen_") for module_id in DESKTOP_BUILTIN_IDS)


def test_bio_modules_register_under_a_trust_store(trusted: DesktopService) -> None:
    assert {SLIME_MOLD_ID, MYCELIUM_ID} <= set(trusted.bio_modules)
    assert {SLIME_MOLD_ID, MYCELIUM_ID} <= set(trusted.stack.registry.list_module_ids())


def test_catalog_module_registers_under_a_trust_store(trusted: DesktopService) -> None:
    assert trusted.register_catalog_module("hdc_module")["registered"] is True


def test_core_module_registers_under_a_trust_store(trusted: DesktopService) -> None:
    assert trusted.register_core_module("learned")["registered"] is True
