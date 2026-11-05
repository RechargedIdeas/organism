"""Repository hygiene: forbidden paths, conflict markers, secrets, and oversized files.

Hygiene is cheap and never needs the venv, so it runs first in every tier and on every commit.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from organism_ci.environment import Tools

_CONFLICT = re.compile(r"^(?:<<<<<<< |>>>>>>> |=======\r?$)", re.MULTILINE)
_SECRETS = {
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "slack-token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
}
# Detector source and fixtures legitimately contain the patterns above.
_SECRET_EXEMPT = ("ci/organism_ci/", "tests/ci/")
_SNIFF_BYTES = 8192


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    detail: str


def _git_lines(tools: Tools, args: list[str]) -> list[str]:
    if tools.git is None:
        raise RuntimeError("git is not available; hygiene needs it to list files")
    proc = subprocess.run(
        [tools.program("git"), *args],
        cwd=tools.root,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        message = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")
    return [item.decode("utf-8", "replace") for item in proc.stdout.split(b"\0") if item]


def tree_files(tools: Tools) -> list[str]:
    """Tracked files plus untracked files that are not ignored: what would be committed."""
    return _git_lines(tools, ["ls-files", "-z", "-co", "--exclude-standard"])


def staged_files(tools: Tools) -> list[str]:
    return _git_lines(tools, ["diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"])


def _is_forbidden(path: str, patterns: Iterable[str]) -> str | None:
    name = path.rsplit("/", 1)[-1]
    for pattern in patterns:
        if pattern.endswith("/"):
            if path.startswith(pattern):
                return pattern
        elif fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(name, pattern):
            return pattern
    return None


def scan(
    root: Path,
    paths: Iterable[str],
    *,
    forbidden: Iterable[str],
    max_file_mib: float,
) -> list[Finding]:
    """Return every finding. An empty list means the paths are clean."""
    patterns = tuple(forbidden)
    limit = int(max_file_mib * 1024 * 1024)
    findings: list[Finding] = []
    for rel in paths:
        if (hit := _is_forbidden(rel, patterns)) is not None:
            findings.append(Finding(rel, "forbidden-path", f"matches {hit!r}"))
        full = root / rel
        if not full.is_file():
            continue  # deleted in the working tree, or a submodule entry
        size = full.stat().st_size
        if size > limit:
            findings.append(Finding(rel, "large-file", f"{size / 1048576:.1f} MiB"))
        if size == 0:
            continue
        data = full.read_bytes()
        if b"\0" in data[:_SNIFF_BYTES]:
            continue  # binary: conflict markers and text secrets do not apply
        text = data.decode("utf-8", "replace")
        if _CONFLICT.search(text):
            findings.append(Finding(rel, "conflict-marker", "unresolved merge conflict"))
        if not rel.startswith(_SECRET_EXEMPT):
            for name, pattern in _SECRETS.items():
                if pattern.search(text):
                    findings.append(Finding(rel, "secret", f"looks like a {name}"))
    return findings


def render(findings: list[Finding]) -> str:
    return "\n".join(f"{f.path}: [{f.rule}] {f.detail}" for f in findings)
