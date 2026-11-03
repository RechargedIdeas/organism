"""Gate execution, run locking, and the CLI, exercised with real short-lived child processes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from organism_ci import cli, report, runs
from organism_ci.cache import ResultCache, TreeDigest
from organism_ci.config import Gate, load_pipeline
from organism_ci.environment import Tools
from organism_ci.execute import ERROR, FAIL, FLAKY, PASS, SKIP, Context, Executor, parse_counts

ROOT = Path(__file__).resolve().parents[2]


class _FixedDigest(TreeDigest):
    """Stands in for git-based hashing so the cache path runs in a temporary directory."""

    def digest(self, inputs):  # type: ignore[override]
        return "fixed"


def _tools(root: Path) -> Tools:
    return Tools(root=root, python=Path(sys.executable), python_version="test")


def _gate(gate_id: str, command: str, **overrides) -> Gate:
    values = {
        "id": gate_id,
        "tier": "fast",
        "command": command,
        "builtin": None,
        "env": {},
        "blocking": True,
        "exclusive": False,
        "cacheable": False,
        "retries": 0,
        "timeout_s": 60.0,
        "requires": (),
        "inputs": (),
    }
    values.update(overrides)
    return Gate(**values)


def _context(root: Path, *, cache: ResultCache | None = None, fail_fast: bool = False) -> Context:
    tools = _tools(root)
    return Context(
        tools=tools,
        pipeline=load_pipeline(ROOT / "ci" / "pipeline.toml"),
        run=runs.new_run(root, "fast"),
        cache=cache,
        tree=_FixedDigest(tools),
        fail_fast=fail_fast,
    )


def _run_one(root: Path, gate: Gate, **kwargs):
    ctx = _context(root, **kwargs)
    return Executor(ctx).run([gate], jobs=1)[0]


def test_passing_command_is_pass_and_its_log_is_kept(tmp_path):
    result = _run_one(tmp_path, _gate("ok:pass", "{python} -c \"print('hello')\""))
    assert result.status == PASS
    assert result.returncode == 0
    assert "\nhello\n" in (tmp_path / result.log).read_text(encoding="utf-8")


def test_failing_command_is_fail_with_the_tail_as_note(tmp_path):
    result = _run_one(tmp_path, _gate("bad:fail", '{python} -c "import sys; print(\'boom\'); sys.exit(3)"'))
    assert result.status == FAIL
    assert result.returncode == 3
    assert "boom" in result.note


def test_timeout_kills_the_child_and_reports_error(tmp_path):
    gate = _gate("slow:hang", '{python} -c "import time; time.sleep(60)"', timeout_s=1.0)
    result = _run_one(tmp_path, gate)
    assert result.status == ERROR
    assert result.note == "timed out"


def test_missing_requirement_is_skip_and_blocking_skip_counts_as_failing(tmp_path):
    gate = _gate("needs:cargo", "{python} -c 'pass'", requires=("cargo",))
    result = _run_one(tmp_path, gate)
    assert result.status == SKIP
    assert result.note == "missing: cargo"
    assert result.failing is True


def test_retry_that_passes_is_flaky_not_pass(tmp_path):
    marker = tmp_path / "attempts.txt"
    script = (
        "import pathlib, sys\n"
        f"p = pathlib.Path({str(marker)!r})\n"
        "n = int(p.read_text()) if p.exists() else 0\n"
        "p.write_text(str(n + 1))\n"
        "sys.exit(0 if n >= 1 else 1)\n"
    )
    script_path = tmp_path / "flaky.py"
    script_path.write_text(script, encoding="utf-8")
    # Forward slashes: gate commands are shell-split, where backslashes would be escapes.
    gate = _gate("flaky:once", "{python} " + script_path.as_posix(), retries=2)
    result = _run_one(tmp_path, gate)
    assert result.status == FLAKY
    assert result.attempts == 2
    assert result.failing is False


def test_advisory_failure_is_not_failing(tmp_path):
    result = _run_one(tmp_path, _gate("soft:fail", "{python} -c 'import sys; sys.exit(1)'", blocking=False))
    assert result.status == FAIL
    assert result.failing is False


def test_cache_skips_a_gate_whose_inputs_have_not_changed(tmp_path):
    cache = ResultCache(tmp_path / "cache")
    gate = _gate("cached:pass", "{python} -c 'pass'", cacheable=True)
    first = _run_one(tmp_path, gate, cache=cache)
    second = _run_one(tmp_path, gate, cache=cache)
    assert first.status == PASS
    assert second.status == "CACHED"


def test_fail_fast_skips_gates_scheduled_after_a_failure(tmp_path):
    ctx = _context(tmp_path, fail_fast=True)
    gates = [
        _gate("first:fail", "{python} -c 'import sys; sys.exit(1)'"),
        _gate("second:never", "{python} -c 'pass'"),
    ]
    results = Executor(ctx).run(gates, jobs=1)
    assert [r.status for r in results] == [FAIL, SKIP]
    assert "fail-fast" in results[1].note


def test_results_come_back_in_configuration_order_even_when_run_in_parallel(tmp_path):
    gates = [_gate(f"g:{i}", "{python} -c 'pass'") for i in range(4)]
    results = Executor(_context(tmp_path)).run(gates, jobs=4)
    assert [r.id for r in results] == [g.id for g in gates]


def test_progress_callback_sees_every_result(tmp_path):
    seen: list[str] = []
    ctx = _context(tmp_path)
    Executor(ctx, on_done=lambda r: seen.append(r.id)).run([_gate("a:a", "{python} -c 'pass'")], jobs=1)
    assert seen == ["a:a"]


def test_parse_counts_reads_pytest_summary_line():
    text = "....\n4 failed, 447 passed, 4 skipped, 2 deselected in 72.78s (0:01:12)\n"
    assert parse_counts(text) == {"failed": 4, "passed": 447, "skipped": 4, "deselected": 2}
    assert parse_counts("nothing to see") == {}


def test_run_lock_is_exclusive_and_stale_locks_are_taken_over(tmp_path):
    first = runs.RunLock(tmp_path)
    first.acquire()
    with pytest.raises(runs.LockBusy):
        runs.RunLock(tmp_path).acquire()
    first.release()

    stale = runs.runs_root(tmp_path) / runs.LOCK_NAME
    stale.write_text("999999", encoding="utf-8")  # a pid that should not exist
    taker = runs.RunLock(tmp_path)
    taker.acquire()
    taker.release()
    assert not stale.exists()


def test_prune_keeps_only_the_newest_run_directories(tmp_path):
    base = runs.runs_root(tmp_path)
    names = [f"2026110{day}T100000Z-fast-{day}" for day in range(1, 5)]
    for name in names:
        (base / name).mkdir(parents=True)
    (base / "not-a-run").mkdir()
    removed = runs.prune(tmp_path, keep=2)
    assert sorted(p.name for p in removed) == names[:2]
    assert (base / "not-a-run").is_dir()


def test_report_summary_counts_statuses(tmp_path):
    results = [
        _run_one(tmp_path, _gate("ok:pass", "{python} -c 'pass'")),
        _run_one(tmp_path, _gate("bad:fail", "{python} -c 'import sys; sys.exit(1)'", blocking=False)),
    ]
    summary = report.summarize(results)
    assert summary["passed"] == 1
    assert summary["failed_advisory"] == 1
    assert summary["failed_blocking"] == 0


def test_cli_list_prints_the_selected_gates_and_exits_zero(capsys):
    assert cli.main(["list", "--tier", "precommit"], root=ROOT) == 0
    out = capsys.readouterr().out
    assert "lint:ruff" in out
    assert "suite:fast" not in out


def test_cli_rejects_unknown_only_ids_with_config_exit_code(capsys):
    assert cli.main(["list", "--only", "does:not_exist"], root=ROOT) == 4
    assert "unknown gate id" in capsys.readouterr().out


def test_cli_defaults_to_the_run_command_for_bare_flags(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(cli, "_cmd_run", lambda args, root: calls.append(args.command) or 0)
    assert cli.main(["--tier", "precommit"], root=ROOT) == 0
    assert calls == ["run"]


def test_hook_files_exist_and_use_lf_endings():
    for name in ("pre-commit", "pre-push", "_resolve.sh"):
        data = (ROOT / "ci" / "hooks" / name).read_bytes()
        assert b"\r\n" not in data, name
        assert data.startswith(b"#!/bin/sh"), name
