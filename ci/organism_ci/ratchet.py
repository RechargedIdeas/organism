"""Ratchets: lint and type findings may not grow past a recorded baseline.

The baseline records findings per ``path::code`` key. A run fails when any key is new or
has more findings than recorded. Fixing findings lowers the count and passes. Lowering the
baseline is a deliberate step: ``python ci/run.py baseline <tool>``.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

BASELINE_VERSION = 1

_RUFF = re.compile(r"^(?P<path>.+?):\d+:\d+: (?P<code>[A-Z]+\d+) ")
_MYPY = re.compile(
    r"^(?P<path>[^\s:][^:]*?):\d+(?::\d+)?: error: .*?(?:\s\[(?P<code>[\w-]+)\])?\s*$"
)
_RUSTFMT = re.compile(r"^Diff in (?P<path>.+?):\d+:$")
_WINDOWS_VERBATIM = "\\\\?\\"


def _posix(path: str, root: Path | None) -> str:
    """Repo-relative, forward-slash path. Tools run from the repo root, so relative stays put."""
    cleaned = path.removeprefix(_WINDOWS_VERBATIM).replace("\\", "/")
    if root is not None and Path(cleaned).is_absolute():
        try:
            cleaned = Path(cleaned).relative_to(root).as_posix()
        except ValueError:
            pass
    return cleaned


def parse_ruff(output: str, root: Path | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for line in output.splitlines():
        match = _RUFF.match(line)
        if match:
            counts[f"{_posix(match['path'], root)}::{match['code']}"] += 1
    return dict(counts)


def parse_mypy(output: str, root: Path | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for line in output.splitlines():
        match = _MYPY.match(line)
        if match:
            code = match["code"] or "nocode"
            counts[f"{_posix(match['path'], root)}::{code}"] += 1
    return dict(counts)


def parse_rustfmt(output: str, root: Path | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for line in output.splitlines():
        match = _RUSTFMT.match(line.strip())
        if match:
            counts[_posix(match["path"], root)] += 1
    return dict(counts)


PARSERS = {"ruff": parse_ruff, "mypy": parse_mypy, "rustfmt": parse_rustfmt}


@dataclass
class Outcome:
    """Result of comparing current findings with the baseline."""

    tool: str
    total: int
    baseline_total: int
    regressions: dict[str, tuple[int, int]] = field(default_factory=dict)
    improved_keys: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.regressions and not self.error

    def describe(self) -> str:
        if self.error:
            return f"{self.tool}: {self.error}"
        if self.regressions:
            worst = sorted(self.regressions.items())[:5]
            lines = [f"{self.tool}: {len(self.regressions)} key(s) above baseline"]
            lines += [f"  {key}: {base} -> {now}" for key, (base, now) in worst]
            return "\n".join(lines)
        note = f", {self.improved_keys} improved" if self.improved_keys else ""
        return f"{self.tool}: {self.total} finding(s), within baseline ({self.baseline_total}){note}"


def compare(tool: str, current: dict[str, int], baseline: dict[str, int]) -> Outcome:
    regressions = {
        key: (baseline.get(key, 0), count)
        for key, count in current.items()
        if count > baseline.get(key, 0)
    }
    improved = sum(1 for key, base in baseline.items() if current.get(key, 0) < base)
    return Outcome(
        tool=tool,
        total=sum(current.values()),
        baseline_total=sum(baseline.values()),
        regressions=regressions,
        improved_keys=improved,
    )


def load_baseline(path: Path) -> dict[str, int] | None:
    """Return the recorded counts, or None when no baseline has been written yet."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: unreadable baseline ({exc})") from exc
    counts = data.get("counts") if isinstance(data, dict) else None
    if not isinstance(counts, dict) or not all(
        isinstance(k, str) and isinstance(v, int) and v >= 0 for k, v in counts.items()
    ):
        raise ValueError(f"{path}: baseline must hold a 'counts' mapping of ints")
    return counts


def write_baseline(path: Path, tool: str, counts: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": BASELINE_VERSION,
        "tool": tool,
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": sum(counts.values()),
        "counts": dict(sorted(counts.items())),
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def judge(tool: str, output: str, *, root: Path, baseline_path: Path) -> Outcome:
    """Parse one tool's output and compare it with the stored baseline."""
    current = PARSERS[tool](output, root)
    baseline = load_baseline(baseline_path)
    if baseline is None:
        return Outcome(
            tool=tool,
            total=sum(current.values()),
            baseline_total=0,
            error=f"no baseline at {baseline_path.name}; run: python ci/run.py baseline {tool}",
        )
    return compare(tool, current, baseline)
