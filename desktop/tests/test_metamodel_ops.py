"""Metamodel + ops surfaces via service."""
from __future__ import annotations

from organism_desktop.service import DesktopService


def test_metamodel_path():
    svc = DesktopService.create()
    organ = svc.metamodel_synthesize("ui_organ")
    assert organ["may_actuate"] is False
    assert organ["stage"] == "SYNTHESIZED"
    sand = svc.metamodel_advance(organ["organ_id"], "sandbox")
    assert sand["stage"] == "SANDBOXED"


def test_ops_validate_and_docs():
    svc = DesktopService.create()
    ops = svc.ops_info()
    assert ops["cpu_everywhere"] is True
    assert ops["validate"]["ok"] is True
    assert ops["wetlab_policy"]["actuation_certified"] is False
    links = svc.docs_links()
    assert len(links) >= 4
