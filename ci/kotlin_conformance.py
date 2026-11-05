"""Run the Kotlin SDK's Gradle tests, the conformance:kotlin gate.

The gate runs with no shell, so this launcher picks the wrapper for the OS: gradlew.bat on Windows and
`sh gradlew` elsewhere (the wrapper is stored without its execute bit). Any extra arguments are passed to
`gradlew test`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def wrapper_command(kotlin_dir: Path) -> list[str]:
    """The command that runs the Gradle wrapper for this OS, from the Kotlin SDK folder."""
    if os.name == "nt":
        return [str(kotlin_dir / "gradlew.bat")]
    return ["sh", str(kotlin_dir / "gradlew")]


def main(argv: list[str]) -> int:
    kotlin_dir = Path(__file__).resolve().parent.parent / "sdk" / "kotlin"
    command = [*wrapper_command(kotlin_dir), "--console=plain", "test", *argv]
    return subprocess.call(command, cwd=kotlin_dir)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
