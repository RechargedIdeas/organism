"""Build bench/data/intent_routing.json from the MoA routing sets under sdk/python/tests/data.

The six routing sets are merged. The guardrail set is left out. A query that appears in more than
one set is kept once, under the first set that holds it. Each row keeps its source file, so the
baseline can be split by origin. The output is deterministic: the sets are read in sorted order.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sdk" / "python" / "tests" / "data"
OUT = ROOT / "bench" / "data" / "intent_routing.json"
LABELS = {"intent_classifier", "extractor", "unsure"}


def build() -> list[dict[str, object]]:
    seen: set[str] = set()
    rows: list[dict[str, object]] = []
    for path in sorted(SOURCE.glob("moa_routing_*.json")):
        for raw in json.loads(path.read_text(encoding="utf-8")):
            label = raw["label"]
            if label not in LABELS:
                raise ValueError(f"{path.name}: unknown label {label!r}")
            key = " ".join(raw["query"].split()).lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "id": f"r{len(rows) + 1:03d}",
                    "query": raw["query"],
                    "form": raw.get("form"),
                    "label": label,
                    "source": path.name,
                }
            )
    return rows


def main() -> int:
    rows = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} rows to {OUT}")
    print("labels:", dict(Counter(str(row["label"]) for row in rows)))
    print("sources:", dict(Counter(str(row["source"]) for row in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
