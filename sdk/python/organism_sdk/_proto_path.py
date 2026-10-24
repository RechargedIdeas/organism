"""Ensure generated protobuf packages are importable as organism.v1.*."""
from __future__ import annotations

import sys
from pathlib import Path

_ADDED = False


def ensure_proto_path() -> Path:
    global _ADDED
    root = Path(__file__).resolve().parent / "_proto"
    if not _ADDED:
        s = str(root)
        if s not in sys.path:
            sys.path.insert(0, s)
        _ADDED = True
    return root
