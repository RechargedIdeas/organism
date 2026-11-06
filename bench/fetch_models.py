"""Download the candidate encoders and pin each one to a commit.

Reads bench/models.toml. Each model goes into bench/models/<name> at the commit recorded in
bench/models.lock.json, so every benchmark run sees the same weights. A model with no lock entry
is resolved to the repo's current commit and recorded. Pass --update to re-resolve every model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, snapshot_download
from organism_bench.specs import LOCK, MODELS_DIR, ModelSpec, load_lock, load_models

# Formats the benchmark never loads. Skipping them keeps the downloads to the PyTorch weights.
IGNORE = [
    "*.onnx",
    "*.onnx_data",
    "onnx/*",
    "openvino/*",
    "*.tflite",
    "*.msgpack",
    "*.h5",
    "*.ot",
    "*.gguf",
    "tf_model*",
    "flax_model*",
    "rust_model*",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _license(info: Any) -> str:
    card = getattr(info, "card_data", None)
    license_field = getattr(card, "license", None)
    if isinstance(license_field, list):
        return ", ".join(str(item) for item in license_field)
    return str(license_field) if license_field else "unknown"


def _download(spec: ModelSpec, locked_revision: str | None, api: HfApi) -> dict[str, Any]:
    info = api.model_info(spec.repo, revision=locked_revision)
    snapshot_download(
        repo_id=spec.repo,
        revision=info.sha,
        local_dir=spec.path,
        ignore_patterns=IGNORE,
    )
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(spec.path.rglob("*")):
        rel = path.relative_to(spec.path)
        if not path.is_file() or ".cache" in rel.parts:
            continue
        files[rel.as_posix()] = {"size": path.stat().st_size, "sha256": _sha256(path)}
    return {
        "repo": spec.repo,
        "kind": spec.kind,
        "revision": info.sha,
        "license": _license(info),
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="comma-separated model names to fetch")
    parser.add_argument("--update", action="store_true", help="re-resolve every repo")
    args = parser.parse_args(argv)
    wanted = set(args.only.split(",")) if args.only else None

    lock = load_lock()
    api = HfApi()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for spec in load_models():
        if wanted is not None and spec.name not in wanted:
            continue
        locked = None if args.update else lock.get(spec.name, {}).get("revision")
        print(f"fetching {spec.name} from {spec.repo} ...", flush=True)
        entry = _download(spec, locked, api)
        entry["fetched_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        lock[spec.name] = entry
        size_mb = sum(f["size"] for f in entry["files"].values()) / 1e6
        print(f"  {entry['revision'][:12]}  {entry['license']}  {size_mb:.1f} MB", flush=True)
    LOCK.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {LOCK}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
