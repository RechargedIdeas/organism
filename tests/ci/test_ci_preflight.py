"""Preflight's protobuf staleness check: generated modules must be found where protoc writes them."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from organism_ci.config import Pipeline, Proto, load_pipeline
from organism_ci.environment import Tools
from organism_ci.preflight import _proto_stale

ROOT = Path(__file__).resolve().parents[2]


def _setup(root: Path) -> tuple[Tools, Pipeline]:
    proto_dir = root / "proto" / "organism" / "v1"
    proto_dir.mkdir(parents=True)
    (proto_dir / "bus.proto").write_text('syntax = "proto3";\n', encoding="utf-8")
    base = load_pipeline(ROOT / "ci" / "pipeline.toml")
    return Tools(root=root), replace(base, proto=Proto(source="proto/organism/v1", output="out"))


def _generate(root: Path, relative: str) -> Path:
    target = root / "out" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# generated\n", encoding="utf-8")
    return target


def test_missing_generated_module_is_stale(tmp_path: Path) -> None:
    tools, pipeline = _setup(tmp_path)
    assert _proto_stale(tools, pipeline) == ["bus.proto"]


def test_module_at_the_path_protoc_writes_is_current(tmp_path: Path) -> None:
    # protoc mirrors the include path, so bus.proto lands under organism/v1/.
    tools, pipeline = _setup(tmp_path)
    _generate(tmp_path, "organism/v1/bus_pb2.py")
    assert _proto_stale(tools, pipeline) == []


def test_flat_module_path_is_not_mistaken_for_current(tmp_path: Path) -> None:
    tools, pipeline = _setup(tmp_path)
    _generate(tmp_path, "bus_pb2.py")
    assert _proto_stale(tools, pipeline) == ["bus.proto"]


def test_generated_module_older_than_its_proto_is_stale(tmp_path: Path) -> None:
    tools, pipeline = _setup(tmp_path)
    generated = _generate(tmp_path, "organism/v1/bus_pb2.py")
    proto = tmp_path / "proto" / "organism" / "v1" / "bus.proto"
    earlier = proto.stat().st_mtime - 10
    os.utime(generated, (earlier, earlier))
    assert _proto_stale(tools, pipeline) == ["bus.proto"]
