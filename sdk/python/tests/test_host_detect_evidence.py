"""Container and VM evidence rules in organism_sdk.host.detect, driven by fake host files.

The detector reads a fixed set of paths. These tests replace those reads, so each branch runs the
same way on every platform and never depends on the machine running the suite.
"""
from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from organism_sdk.host import detect

ROOT = Path(__file__).resolve().parents[3]
CONTAINER_ENV = (
    "ORGANISM_FORCE_HOST_KIND",
    "container",
    "CONTAINER",
    "KUBERNETES_SERVICE_HOST",
    "PODMAN_CONTAINER",
)
FakeHost = Callable[..., None]


@pytest.fixture
def fake_host(monkeypatch: pytest.MonkeyPatch) -> FakeHost:
    """Install fake files and existing paths; returns a setter for them."""
    for key in CONTAINER_ENV:
        monkeypatch.delenv(key, raising=False)
    state: dict[str, Any] = {"files": {}, "existing": set()}

    def read_text(path: Path, limit: int = 65536) -> str | None:
        found: str | None = state["files"].get(path.as_posix())
        return found

    def exists(self: Path) -> bool:
        return self.as_posix() in state["existing"]

    monkeypatch.setattr(detect, "_read_text", read_text)
    monkeypatch.setattr(Path, "exists", exists)

    def configure(files: dict[str, str] | None = None, existing: set[str] | None = None) -> None:
        state["files"] = files or {}
        state["existing"] = existing or set()

    return configure


def test_no_evidence_means_not_a_container(fake_host: FakeHost) -> None:
    fake_host()
    assert detect._detect_container() == (False, None, [])


def test_dockerenv_marks_docker(fake_host: FakeHost) -> None:
    fake_host(existing={"/.dockerenv"})
    in_container, runtime, evidence = detect._detect_container()
    assert in_container is True
    assert runtime == "docker"
    assert "/.dockerenv" in evidence


def test_containerenv_marks_podman(fake_host: FakeHost) -> None:
    fake_host(existing={"/run/.containerenv"})
    _, runtime, evidence = detect._detect_container()
    assert runtime == "podman"
    assert "/run/.containerenv" in evidence


@pytest.mark.parametrize(
    ("cgroup", "runtime"),
    [
        ("12:cpu:/docker/abc123", "docker"),
        ("0::/libpod-4f2e", "podman"),
        ("0::/crio-9a1", "cri-o"),
        ("0::/kubepods/burstable/pod-1234", "containerd"),
    ],
)
def test_cgroup_markers_name_the_runtime(fake_host: FakeHost, cgroup: str, runtime: str) -> None:
    fake_host(files={"/proc/1/cgroup": cgroup})
    in_container, detected, evidence = detect._detect_container()
    assert in_container is True
    assert detected == runtime
    assert "cgroup:container_marker" in evidence


def test_kubernetes_env_names_containerd(fake_host: FakeHost, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    fake_host()
    _, runtime, evidence = detect._detect_container()
    assert runtime == "containerd"
    assert "env:KUBERNETES_SERVICE_HOST" in evidence


def test_pid1_name_alone_is_a_weak_signal(fake_host: FakeHost) -> None:
    # Without any other evidence, a non-init PID 1 must not count as a container.
    fake_host(files={"/proc/1/cmdline": "/app/server\x00--port\x008080"})
    assert detect._detect_container() == (False, None, [])


def test_pid1_name_counts_when_other_evidence_exists(fake_host: FakeHost) -> None:
    fake_host(
        existing={"/.dockerenv"},
        files={"/proc/1/cmdline": "/app/server\x00--port\x008080"},
    )
    _, _, evidence = detect._detect_container()
    assert "pid1:/app/server" in evidence


def test_mountinfo_path_is_unknown_runtime(fake_host: FakeHost) -> None:
    fake_host(files={"/proc/self/mountinfo": "1 0 8:1 / /var/lib/docker/containers/x"})
    in_container, runtime, evidence = detect._detect_container()
    assert in_container is True
    assert runtime == "unknown"
    assert "mountinfo:container_path" in evidence


def test_no_hypervisor_markers_means_bare_metal(fake_host: FakeHost) -> None:
    fake_host(files={"/proc/cpuinfo": "flags : fpu vme de pse"})
    assert detect._detect_vm() == (False, None, [])


@pytest.mark.parametrize(
    ("vendor", "hypervisor"),
    [("VMware, Inc.", "vmware"), ("QEMU", "qemu"), ("Microsoft Corporation", "hyper-v")],
)
def test_dmi_vendor_names_the_hypervisor(fake_host: FakeHost, vendor: str, hypervisor: str) -> None:
    fake_host(files={"/sys/class/dmi/id/sys_vendor": f"{vendor}\n"})
    is_vm, detected, evidence = detect._detect_vm()
    assert is_vm is True
    assert detected == hypervisor
    assert any(item.startswith("dmi:") for item in evidence)


def test_cpu_hypervisor_flag_is_unknown_when_vendor_is_hidden(fake_host: FakeHost) -> None:
    fake_host(files={"/proc/cpuinfo": "flags : fpu hypervisor sse2"})
    is_vm, detected, evidence = detect._detect_vm()
    assert is_vm is True
    assert detected == "unknown"
    assert "cpuinfo:hypervisor" in evidence


def test_module_entry_point_prints_help() -> None:
    # `python -m organism_sdk` must start the CLI, not fail on import.
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "sdk" / "python")
    proc = subprocess.run(
        [sys.executable, "-m", "organism_sdk", "--help"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "usage" in proc.stdout.lower()
