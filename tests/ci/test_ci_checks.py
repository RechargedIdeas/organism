"""Ratchets, hygiene scans, and the result cache: the checks that decide pass or fail."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from organism_ci import hygiene, ratchet
from organism_ci.cache import ResultCache, cache_key
from organism_ci.environment import Tools

RUFF_OUT = (
    "sdk/python/organism_sdk/a.py:3:1: UP017 Use `datetime.UTC`\n"
    "sdk/python/organism_sdk/a.py:9:1: UP017 Use `datetime.UTC`\n"
    "modules/m.py:1:8: F401 `os` imported but unused\n"
    "Found 3 errors.\n"
)
MYPY_OUT = (
    'sdk\\python\\organism_sdk\\a.py:133: error: Use "-> None" [func-returns-value]\n'
    "sdk/python/organism_sdk/a.py:140: note: something informational\n"
    "sdk/python/organism_sdk/b.py:7: error: Incompatible types\n"
    "Found 2 errors in 2 files (checked 3 source files)\n"
)
RUSTFMT_OUT = (
    "Diff in \\\\?\\H:\\Projects\\Organism\\runtime\\registry\\src\\lib.rs:85:\n"
    "     initial: LifecycleState,\n"
    "Diff in \\\\?\\H:\\Projects\\Organism\\runtime\\registry\\src\\lib.rs:120:\n"
)


def test_ruff_parser_counts_per_path_and_code():
    assert ratchet.parse_ruff(RUFF_OUT) == {
        "sdk/python/organism_sdk/a.py::UP017": 2,
        "modules/m.py::F401": 1,
    }


def test_mypy_parser_normalises_windows_paths_and_skips_notes():
    counts = ratchet.parse_mypy(MYPY_OUT)
    assert counts == {
        "sdk/python/organism_sdk/a.py::func-returns-value": 1,
        "sdk/python/organism_sdk/b.py::nocode": 1,
    }


def test_rustfmt_parser_counts_hunks_per_file_and_strips_verbatim_prefix():
    counts = ratchet.parse_rustfmt(RUSTFMT_OUT, root=None)
    assert counts == {"H:/Projects/Organism/runtime/registry/src/lib.rs": 2}


def test_compare_flags_new_keys_and_increases_but_not_decreases():
    outcome = ratchet.compare(
        "ruff",
        current={"a.py::F401": 3, "b.py::E501": 1, "c.py::UP017": 1},
        baseline={"a.py::F401": 2, "c.py::UP017": 4},
    )
    assert outcome.regressions == {"a.py::F401": (2, 3), "b.py::E501": (0, 1)}
    assert outcome.improved_keys == 1
    assert not outcome.ok


def test_compare_passes_when_findings_only_go_down():
    outcome = ratchet.compare("mypy", current={"a.py::x": 1}, baseline={"a.py::x": 5, "b.py::y": 2})
    assert outcome.ok
    assert outcome.improved_keys == 2


def test_judge_without_a_baseline_is_an_error_with_the_fix_command(tmp_path):
    outcome = ratchet.judge("ruff", RUFF_OUT, root=tmp_path, baseline_path=tmp_path / "ruff.json")
    assert outcome.error
    assert "python ci/run.py baseline ruff" in outcome.error


def test_baseline_round_trips_and_rejects_malformed_files(tmp_path):
    path = tmp_path / "ruff.json"
    ratchet.write_baseline(path, "ruff", {"a.py::F401": 2})
    assert ratchet.load_baseline(path) == {"a.py::F401": 2}
    path.write_text(json.dumps({"counts": {"a": "two"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="counts"):
        ratchet.load_baseline(path)


def _tools(root: Path) -> Tools:
    return Tools(root=root)


def test_hygiene_flags_forbidden_paths_conflicts_and_secrets(tmp_path):
    (tmp_path / "chat_archive").mkdir()
    (tmp_path / "chat_archive" / "x.md").write_text("hello", encoding="utf-8")
    (tmp_path / "notes.trace").write_text("t", encoding="utf-8")
    (tmp_path / "clean.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "merge.py").write_bytes(b"a\r\n<<<<<<< HEAD\r\nb\r\n=======\r\nc\r\n>>>>>>> other\r\n")
    (tmp_path / "keys.py").write_text("KEY = 'AKIA" + "A" * 16 + "'\n", encoding="utf-8")
    findings = hygiene.scan(
        tmp_path,
        ["chat_archive/x.md", "notes.trace", "clean.py", "merge.py", "keys.py"],
        forbidden=["chat_archive/", "*.trace"],
        max_file_mib=5,
    )
    rules = {(f.path, f.rule) for f in findings}
    assert ("chat_archive/x.md", "forbidden-path") in rules
    assert ("notes.trace", "forbidden-path") in rules
    assert ("merge.py", "conflict-marker") in rules
    assert ("keys.py", "secret") in rules
    assert not any(f.path == "clean.py" for f in findings)


def test_hygiene_ignores_binary_files_and_exempt_detector_source(tmp_path):
    (tmp_path / "blob.bin").write_bytes(b"\0AKIA" + b"A" * 16)
    (tmp_path / "ci" / "organism_ci").mkdir(parents=True)
    (tmp_path / "ci" / "organism_ci" / "patterns.py").write_text("AKIA" + "B" * 16, encoding="utf-8")
    findings = hygiene.scan(
        tmp_path, ["blob.bin", "ci/organism_ci/patterns.py"], forbidden=[], max_file_mib=5
    )
    assert findings == []


def test_hygiene_reports_files_over_the_size_limit(tmp_path):
    (tmp_path / "big.dat").write_bytes(b"x" * (2 * 1024 * 1024))
    findings = hygiene.scan(tmp_path, ["big.dat"], forbidden=[], max_file_mib=1)
    assert [f.rule for f in findings] == ["large-file"]


def test_cache_key_changes_with_any_input():
    tools = _tools(Path("."))
    base = {
        "gate_id": "g",
        "argv": ("py", "-m", "pytest"),
        "env": {"A": "1"},
        "tools": tools,
        "tree_digest": "t1",
    }
    key = cache_key(**base)
    assert key == cache_key(**base)
    assert key != cache_key(**{**base, "tree_digest": "t2"})
    assert key != cache_key(**{**base, "env": {"A": "2"}})
    assert key != cache_key(**{**base, "argv": ("py", "-m", "ruff")})


def test_cache_hits_only_on_matching_key_and_passing_status(tmp_path):
    cache = ResultCache(tmp_path / "cache")
    assert cache.get("v1:x", "k1") is None
    cache.put("v1:x", "k1", duration_s=1.5)
    assert cache.get("v1:x", "k1") is not None
    assert cache.get("v1:x", "other") is None
    doc = json.loads((tmp_path / "cache" / "v1__x.json").read_text(encoding="utf-8"))
    doc["entries"][0]["status"] = "FAIL"
    (tmp_path / "cache" / "v1__x.json").write_text(json.dumps(doc), encoding="utf-8")
    assert cache.get("v1:x", "k1") is None


def test_a_corrupt_cache_file_is_a_miss_not_an_error(tmp_path):
    cache = ResultCache(tmp_path)
    (tmp_path / "g.json").write_text("{not json", encoding="utf-8")
    assert cache.get("g", "k") is None
