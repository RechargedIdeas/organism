"""Check that the checked-in conformance vectors are what the Python reference generator produces.

This is the conformance:regen gate. The generator writes into a temporary folder, and every vector there must match the
checked-in file of the same name byte for byte. A missing or extra file also fails. Without this check, the vectors could
drift from the reference, and the Kotlin and Rust ports would keep passing against stale data. Run with --vectors DIR to
check another folder.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATOR = ROOT / "conformance" / "generate.py"
DEFAULT_VECTORS = ROOT / "conformance" / "vectors"


def diff_folders(checked_in: Path, generated: Path) -> list[str]:
    """The problems between two folders of JSON vectors. Empty when they match."""
    want = {p.name for p in checked_in.glob("*.json")}
    got = {p.name for p in generated.glob("*.json")}
    problems = [f"checked in but not produced by the generator: {name}" for name in sorted(want - got)]
    problems += [f"produced by the generator but not checked in: {name}" for name in sorted(got - want)]
    for name in sorted(want & got):
        if (checked_in / name).read_bytes() != (generated / name).read_bytes():
            problems.append(f"differs from the generator output: {name}")
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check the checked-in conformance vectors against the generator.")
    parser.add_argument("--vectors", type=Path, default=DEFAULT_VECTORS, help="folder of checked-in vectors")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        run = subprocess.run([sys.executable, str(GENERATOR), tmp], cwd=ROOT, capture_output=True, text=True, check=False)
        if run.returncode != 0:
            print("conformance:regen: the generator failed", file=sys.stderr)
            print(run.stderr, file=sys.stderr)
            return run.returncode
        problems = diff_folders(args.vectors, Path(tmp))
        count = len(list(Path(tmp).glob("*.json")))

    if problems:
        print("conformance:regen: checked-in vectors do not match the generator:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print("Regenerate only with a reviewed reference change (docs/INTEROP.md), never by hand.", file=sys.stderr)
        return 1
    print(f"conformance:regen: {count} vectors match the generator")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
