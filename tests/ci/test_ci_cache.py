"""The result cache keeps several passing keys per gate, so two environments do not evict each other."""

from __future__ import annotations

import json
from pathlib import Path

from organism_ci.cache import MAX_ENTRIES, ResultCache


def test_two_environments_keep_their_own_entries(tmp_path: Path) -> None:
    # Regression: a terminal run and a git hook run took turns overwriting one entry per gate.
    cache = ResultCache(tmp_path)
    cache.put("lint:ruff", "terminal-key", duration_s=1.0)
    cache.put("lint:ruff", "hook-key", duration_s=1.0)
    assert cache.get("lint:ruff", "terminal-key") is not None
    assert cache.get("lint:ruff", "hook-key") is not None


def test_only_the_most_recent_keys_are_kept(tmp_path: Path) -> None:
    cache = ResultCache(tmp_path)
    keys = [f"key-{n}" for n in range(MAX_ENTRIES + 2)]
    for key in keys:
        cache.put("gate:a", key, duration_s=0.1)
    assert cache.get("gate:a", keys[0]) is None
    assert cache.get("gate:a", keys[1]) is None
    assert all(cache.get("gate:a", key) is not None for key in keys[2:])


def test_putting_a_known_key_again_does_not_duplicate_it(tmp_path: Path) -> None:
    cache = ResultCache(tmp_path)
    cache.put("gate:a", "k", duration_s=0.1)
    cache.put("gate:a", "k", duration_s=0.2)
    doc = json.loads((tmp_path / "gate__a.json").read_text(encoding="utf-8"))
    assert [entry["key"] for entry in doc["entries"]] == ["k"]


def test_a_single_entry_file_from_before_is_still_read(tmp_path: Path) -> None:
    (tmp_path / "gate__a.json").write_text(json.dumps({"key": "old", "status": "PASS"}), encoding="utf-8")
    cache = ResultCache(tmp_path)
    assert cache.get("gate:a", "old") is not None
    cache.put("gate:a", "new", duration_s=0.1)
    assert cache.get("gate:a", "old") is not None
    assert cache.get("gate:a", "new") is not None


def test_a_damaged_or_unexpected_file_is_a_miss_and_is_replaced(tmp_path: Path) -> None:
    cache = ResultCache(tmp_path)
    (tmp_path / "gate__a.json").write_text("{not json", encoding="utf-8")
    assert cache.get("gate:a", "k") is None
    (tmp_path / "gate__a.json").write_text(json.dumps({"entries": "nope"}), encoding="utf-8")
    assert cache.get("gate:a", "k") is None
    cache.put("gate:a", "k", duration_s=0.1)
    assert cache.get("gate:a", "k") is not None
