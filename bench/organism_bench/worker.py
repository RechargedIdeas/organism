"""Benchmark one encoder in its own process, then write its JSON result.

run_bench.py starts one worker per model, one after another, so each model's memory and thread
use is measured alone. The thread count is passed to torch after the encoder loads, and set in the
environment before torch is imported. numpy is already loaded by then, so its BLAS threads are not
controlled here; the probe fits are small enough that this does not matter.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from organism_bench.measure import measure_one
from organism_bench.specs import find_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="model name from bench/models.toml")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args(argv)

    os.environ["OMP_NUM_THREADS"] = str(args.threads)
    os.environ["MKL_NUM_THREADS"] = str(args.threads)
    result = measure_one(
        find_model(args.name), folds=args.folds, seeds=args.seeds, threads=args.threads
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{args.name}: wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
