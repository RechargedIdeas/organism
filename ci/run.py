"""Organism local CI pipeline. Run ``python ci/run.py --help`` for the commands.

This file is the only entry point. If PyYAML is missing from the interpreter that started it,
the pipeline re-runs itself under the project's ``.venv`` so the same command works everywhere.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _venv_python() -> Path | None:
    for candidate in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if candidate.is_file():
            return candidate
    return None


def _has_yaml() -> bool:
    try:
        import yaml  # noqa: F401
    except ImportError:
        return False
    return True


if __name__ == "__main__":
    if not _has_yaml():
        venv = _venv_python()
        if venv is None or venv.resolve() == Path(sys.executable).resolve():
            sys.stderr.write(
                "ci: PyYAML is missing. Install it with: .venv/Scripts/python -m pip install pyyaml\n"
            )
            raise SystemExit(4)
        raise SystemExit(subprocess.run([str(venv), __file__, *sys.argv[1:]], check=False).returncode)

    sys.path.insert(0, str(HERE))
    from organism_ci.cli import main

    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    raise SystemExit(main(sys.argv[1:], root=ROOT))
