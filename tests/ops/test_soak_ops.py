"""v1.4 soak ops: runbook present + reconstructibility helper + script."""
from __future__ import annotations

from pathlib import Path

from harness.scenarios.v04_soak import (
    run_soak,
    soak_reconstructibility_ok,
)

ROOT = Path(__file__).resolve().parents[2]


def test_soak_runbook_exists():
    p = ROOT / "docs" / "ops" / "SOAK_RUNBOOK.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "ORGANISM_SOAK_FULL" in text
    assert "PERF.md" in text


def test_soak_target_script_executable():
    s = ROOT / "scripts" / "soak_target.sh"
    assert s.is_file()
    assert s.stat().st_mode & 0o111
    text = s.read_text(encoding="utf-8")
    assert "test_v04_soak" in text


def test_soak_reconstructibility_helper():
    r = run_soak(windows=12, max_bindings=32)
    assert soak_reconstructibility_ok(r)
    assert r.routing_trace_count >= r.plans
    assert not r.flapping
