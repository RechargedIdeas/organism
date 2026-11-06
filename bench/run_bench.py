"""Benchmark every candidate encoder, one at a time, and write the results and a comparison table.

Run from the repository root with the venv interpreter:

    .venv/Scripts/python.exe bench/run_bench.py

Each model runs in its own worker process, in the order listed in bench/models.toml. A model that
fails or has no downloaded weights is recorded with its error and the run goes on. The controls
(majority class and the lexical router) are measured once, in this process.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from organism_bench.measure import controls
from organism_bench.specs import BENCH, load_models

ROOT = BENCH.parent


def _worker_env() -> dict[str, str]:
    env = dict(os.environ)
    paths = [str(BENCH), str(ROOT / "sdk" / "python")]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def _run_worker(name: str, out_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    spec_out = out_dir / f"{name}.json"
    log = out_dir / f"{name}.log"
    command = [
        sys.executable,
        "-m",
        "organism_bench.worker",
        "--name",
        name,
        "--out",
        str(spec_out),
        "--folds",
        str(args.folds),
        "--seeds",
        str(args.seeds),
        "--threads",
        str(args.threads),
    ]
    start = time.perf_counter()
    with log.open("w", encoding="utf-8") as handle:
        proc = subprocess.run(
            command,
            cwd=BENCH,
            env=_worker_env(),
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = round(time.perf_counter() - start, 1)
    if proc.returncode != 0:
        return {
            "name": name,
            "error": f"worker exited {proc.returncode}; see {log.name}",
            "seconds": elapsed,
        }
    result: dict[str, Any] = json.loads(spec_out.read_text(encoding="utf-8"))
    result["seconds"] = elapsed
    return result


def _cell(value: float) -> str:
    return f"{value:.3f}"


def _table(results: list[dict[str, Any]], control: dict[str, Any]) -> str:
    lines = [
        "| model | dim | params | load s | peak RSS MB | p50 ms | rows/s | accuracy | macro-F1 | wrong route | recall extractor | recall intent | recall unsure |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    ranked = sorted(
        (r for r in results if "scores" in r),
        key=lambda r: -r["scores"]["macro_f1"]["mean"],
    )
    for r in ranked:
        s = r["scores"]
        lines.append(
            f"| {r['name']} | {r['dim']} | {r['params'] / 1e6:.1f}M | {r['load_s']} | "
            f"{r['peak_rss_mb']} | {r['latency_ms']['p50']} | {r['batch_rows_per_s']} | "
            f"{_cell(s['accuracy']['mean'])} +/- {_cell(s['accuracy']['std'])} | "
            f"{_cell(s['macro_f1']['mean'])} +/- {_cell(s['macro_f1']['std'])} | "
            f"{_cell(s['wrong_route']['mean'])} | {_cell(s['recall_extractor']['mean'])} | "
            f"{_cell(s['recall_intent_classifier']['mean'])} | {_cell(s['recall_unsure']['mean'])} |"
        )
    for label, key in (
        ("majority class (control)", "majority_class"),
        ("lexical router (control)", "lexical_router"),
    ):
        s = control[key]
        lines.append(
            f"| {label} | - | - | - | - | - | - | "
            f"{_cell(s['accuracy']['mean'])} +/- {_cell(s['accuracy']['std'])} | "
            f"{_cell(s['macro_f1']['mean'])} +/- {_cell(s['macro_f1']['std'])} | "
            f"{_cell(s['wrong_route']['mean'])} | {_cell(s['recall_extractor']['mean'])} | "
            f"{_cell(s['recall_intent_classifier']['mean'])} | {_cell(s['recall_unsure']['mean'])} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--models", help="comma-separated model names; default is every model")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument(
        "--out", type=Path, help="output directory; default bench/results/<UTC time>"
    )
    args = parser.parse_args(argv)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    # Resolved here: the workers run from bench/, so a relative path would land somewhere else.
    out_dir = (args.out or (BENCH / "results" / stamp)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    wanted = set(args.models.split(",")) if args.models else None
    specs = [spec for spec in load_models() if wanted is None or spec.name in wanted]
    control = controls(folds=args.folds, seeds=args.seeds)
    (out_dir / "controls.json").write_text(
        json.dumps(control, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    results: list[dict[str, Any]] = []
    for spec in specs:
        if not spec.path.exists():
            results.append(
                {"name": spec.name, "error": "weights not downloaded; run bench/fetch_models.py"}
            )
            print(f"{spec.name}: skipped, weights not downloaded", flush=True)
            continue
        print(f"{spec.name}: benchmarking ...", flush=True)
        result = _run_worker(spec.name, out_dir, args)
        results.append(result)
        print(
            f"{spec.name}: {'error: ' + result['error'] if 'error' in result else 'done'}",
            flush=True,
        )

    summary = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "folds": args.folds,
        "seeds": args.seeds,
        "threads": args.threads,
        "rows": control["rows"],
        "controls": control,
        "models": results,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "summary.md").write_text(_table(results, control), encoding="utf-8")
    print((out_dir / "summary.md").read_text(encoding="utf-8"), flush=True)
    print(f"results in {out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
