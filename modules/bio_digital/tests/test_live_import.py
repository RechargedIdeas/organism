"""Phase 1 — live Hybrid import vs stub fallback."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bio_digital.vendor_loader import (
    DEFAULT_HYBRID_ROOT,
    clear_hybrid_cache,
    hybrid_root_present,
    load_hybrid,
    resolve_hybrid_root,
)
from bio_digital.hal import BioDigitalHAL
from bio_digital.limits import PHYSARUM_LIMITS, MYCELIUM_LIMITS
from bio_digital.slime_mold import SlimeMoldModule
from bio_digital.mycelium import MyceliumModule


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_hybrid_cache()
    yield
    clear_hybrid_cache()


def test_resolve_default_root_when_present():
    if DEFAULT_HYBRID_ROOT.is_dir():
        assert resolve_hybrid_root() == DEFAULT_HYBRID_ROOT.resolve()
        assert hybrid_root_present()
    else:
        pytest.skip("default Hybrid checkout absent")


def test_live_import_when_root_present(monkeypatch):
    if not DEFAULT_HYBRID_ROOT.is_dir():
        pytest.skip("Hybrid checkout absent")
    monkeypatch.delenv("BIO_DIGITAL_HYBRID_ROOT", raising=False)
    clear_hybrid_cache()
    bundle = load_hybrid(force_reload=True)
    assert bundle.is_live
    assert bundle.SlimeMoldNode is not None
    assert bundle.MyceliumNode is not None
    assert bundle.SimulatedSensorSubsystem is not None
    hal = BioDigitalHAL(PHYSARUM_LIMITS, backend="live")
    assert hal.backend == "live"
    slime = SlimeMoldModule(backend="live")
    assert slime.backend == "live"
    assert slime.execute_logic_gate(1.0, 0.0) == 1.0
    myc = MyceliumModule(backend="live")
    assert myc.backend == "live"
    out = myc.process_spike_train([0.4, 0.1])
    assert isinstance(out, list) and len(out) == 2
    hr = slime.health()
    assert hr.probes.get("backend") == "live"
    assert hr.probes.get("affects_control") is False


def test_stub_when_root_missing(monkeypatch, tmp_path):
    missing = tmp_path / "no-hybrid"
    monkeypatch.setenv("BIO_DIGITAL_HYBRID_ROOT", str(missing))
    clear_hybrid_cache()
    assert resolve_hybrid_root() is None
    bundle = load_hybrid(force_reload=True)
    assert not bundle.is_live
    assert bundle.error == "hybrid_root_missing"
    # Force stub modules even if default path exists on disk
    slime = SlimeMoldModule(backend="stub")
    assert slime.backend == "stub"
    assert slime.execute_logic_gate(1.0, 1.0) == 0.0
    myc = MyceliumModule(backend="stub")
    assert myc.backend == "stub"
    hal = BioDigitalHAL(MYCELIUM_LIMITS, backend="stub")
    assert hal.backend == "stub"
    twin = hal.sample_twin()
    assert twin["backend"] == "stub"
    assert twin["affects_control"] is False


def test_explicit_env_root(monkeypatch):
    if not DEFAULT_HYBRID_ROOT.is_dir():
        pytest.skip("Hybrid checkout absent")
    monkeypatch.setenv("BIO_DIGITAL_HYBRID_ROOT", str(DEFAULT_HYBRID_ROOT))
    clear_hybrid_cache()
    root = resolve_hybrid_root()
    assert root is not None
    assert Path(root) == DEFAULT_HYBRID_ROOT.resolve()
    bundle = load_hybrid(force_reload=True)
    assert bundle.is_live
