"""The v0.4 public Python surface stays exported.

The frozen names are read from docs/API_FREEZE_v0.4.md, so the document stays the source of truth.
Removing or renaming one of them is a breaking change and needs a major bump, so this test
fails before the change ships.
"""
from __future__ import annotations

import re
from pathlib import Path

import organism_sdk

ROOT = Path(__file__).resolve().parents[3]
FREEZE_DOC = ROOT / "docs" / "API_FREEZE_v0.4.md"


def _frozen_python_names() -> list[str]:
    text = FREEZE_DOC.read_text(encoding="utf-8")
    start = text.index("## Frozen: public Python SDK")
    end = text.index("## Experimental")
    names: list[str] = []
    for line in text[start:end].splitlines():
        if line.startswith("`"):
            names += re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", line)
    return names


def test_freeze_section_lists_the_expected_surface() -> None:
    names = _frozen_python_names()
    assert len(names) >= 40, names
    assert "SubstrateContract" in names
    assert "__version__" in names


def test_every_frozen_name_is_exported_and_importable() -> None:
    names = _frozen_python_names()
    not_exported = [n for n in names if not n.startswith("__") and n not in organism_sdk.__all__]
    not_importable = [n for n in names if not hasattr(organism_sdk, n)]
    assert not not_exported, not_exported
    assert not not_importable, not_importable
