"""One release version across the Python packages, the SDK, and the Rust workspace."""
from __future__ import annotations

import tomllib
from pathlib import Path

import organism_sdk

ROOT = Path(__file__).resolve().parents[3]


def _pyproject_version(path: Path) -> str:
    return str(tomllib.loads(path.read_text(encoding="utf-8"))["project"]["version"])


def test_python_packages_and_sdk_report_the_same_version() -> None:
    versions = {
        "root pyproject": _pyproject_version(ROOT / "pyproject.toml"),
        "sdk pyproject": _pyproject_version(ROOT / "sdk" / "python" / "pyproject.toml"),
        "organism_sdk.__version__": organism_sdk.__version__,
    }
    assert len(set(versions.values())) == 1, versions


def test_rust_workspace_shares_the_python_version() -> None:
    cargo = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    rust_version = str(cargo["workspace"]["package"]["version"])
    assert rust_version == organism_sdk.__version__
