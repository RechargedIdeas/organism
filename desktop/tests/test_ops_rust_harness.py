"""Ops rust status + soak/fuzz harness triggers (v1.6.1)."""
from __future__ import annotations

from pathlib import Path

from organism_desktop.service import DesktopService


def test_rust_runtime_status_readonly():
    svc = DesktopService.create()
    st = svc.rust_runtime_status(probe_cargo=True)
    assert st["read_only"] is True
    assert st["cargo_toml_exists"] is True
    assert st["crates_present"] >= 5
    assert st["crates_expected"] >= 5
    meta = st["cargo_metadata"]
    assert meta.get("probed") is True
    # cargo metadata should succeed in this environment
    if meta.get("returncode") == 0:
        assert meta.get("package_count", 0) >= 5
    ops = svc.ops_info()
    assert "rust_runtime" in ops
    assert ops["rust_runtime"]["crates_present"] >= 1


def test_short_soak_writes_artifact():
    svc = DesktopService.create()
    out = svc.run_short_soak_harness(windows=6)
    assert out["ok"] is True
    assert out["kind"] == "soak"
    path = Path(out["result_path"])
    assert path.is_file()
    assert "soak_" in path.name
    assert out["progress"][-1]["pct"] == 100
    assert svc.last_harness_result()["kind"] == "soak"


def test_short_fuzz_writes_artifact():
    svc = DesktopService.create()
    out = svc.run_short_fuzz_harness(trials=8)
    assert out["ok"] is True
    assert out["kind"] == "fuzz"
    path = Path(out["result_path"])
    assert path.is_file()
    assert out["contracts_rejected"] == 8
    assert out["forgeries_rejected"] >= 1
