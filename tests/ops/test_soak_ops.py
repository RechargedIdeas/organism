"""v1.4 soak ops: runbook present + reconstructibility helper + script."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

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


def _git_index_mode(rel: str) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    listing = subprocess.run(
        [git, "ls-files", "-s", "--", rel],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return listing.split()[0] if listing else None


def test_soak_target_script_executable():
    # Windows has no execute bits, so the mode that Linux checkouts receive comes from the git index.
    # Checking the index keeps this assertion running on every platform instead of skipping on Windows.
    rel = "scripts/soak_target.sh"
    s = ROOT / rel
    assert s.is_file()
    mode = _git_index_mode(rel)
    if mode is None:
        pytest.skip("git is not available to read the index mode")
    assert mode == "100755", mode
    if os.name != "nt":
        assert s.stat().st_mode & 0o111
    text = s.read_text(encoding="utf-8")
    assert "test_v04_soak" in text


def test_soak_reconstructibility_helper():
    r = run_soak(windows=12, max_bindings=32)
    assert soak_reconstructibility_ok(r)
    assert r.routing_trace_count >= r.plans
    assert not r.flapping
