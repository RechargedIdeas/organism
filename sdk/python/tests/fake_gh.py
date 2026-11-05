"""A stand-in for `gh` in tests. It answers `gh api` calls from a fixture.

FAKE_GH_FIXTURE names a JSON file: {"responses": {endpoint: {...}}}. A GET, `api --paginate
<endpoint>`, answers with the endpoint's {"pages": [...]}, or fails when the endpoint's value is
{"error": "..."}. A `since` query value keeps only the items whose updated_at, or else created_at,
is at or after it, as the real endpoints do. A POST, `api -X POST <endpoint> -f body=...`, succeeds
unless the endpoint's {"post": {"error": "..."}} says otherwise.

FAKE_GH_LOG names a file that receives each call's argv, one JSON array per line, so a test can
check exactly what was asked.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs


def main(args: list[str]) -> int:
    with Path(os.environ["FAKE_GH_LOG"]).open("a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\n")
    if len(args) == 6 and args[:3] == ["api", "-X", "POST"]:
        return _post(args[3])
    if len(args) != 3 or args[:2] != ["api", "--paginate"]:
        sys.stderr.write("fake gh serves `api --paginate <endpoint>` and `api -X POST`\n")
        return 2
    path, _, query = args[2].partition("?")
    response = _responses().get(path)
    if response is None:
        sys.stderr.write("HTTP 404: Not Found\n")
        return 1
    if "error" in response:
        sys.stderr.write(f"{response['error']}\n")
        return 1
    since = parse_qs(query).get("since", [None])[0]
    for page in response["pages"]:
        kept = [item for item in page if since is None or _stamp(item) >= since]
        sys.stdout.write(json.dumps(kept) + "\n")
    return 0


def _post(path: str) -> int:
    response = _responses().get(path)
    if response is None:
        sys.stderr.write("HTTP 404: Not Found\n")
        return 1
    outcome = response.get("post", {})
    if "error" in outcome:
        sys.stderr.write(f"{outcome['error']}\n")
        return 1
    sys.stdout.write("{}\n")
    return 0


def _responses() -> dict[str, Any]:
    fixture = json.loads(Path(os.environ["FAKE_GH_FIXTURE"]).read_text(encoding="utf-8"))
    return dict(fixture["responses"])


def _stamp(item: dict[str, Any]) -> str:
    return str(item.get("updated_at") or item.get("created_at"))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
