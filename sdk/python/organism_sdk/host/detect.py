"""Detect whether Organism is running bare metal, in a VM, or in a container.

Detection is best-effort and never assumes Docker. Works on Linux primarily;
macOS/Windows return conservative guesses. CPU Everywhere: no GPU dependency.
"""
from __future__ import annotations

import os
import platform
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

HostKind = Literal["bare_metal", "vm", "container", "unknown"]

HOST_KINDS: tuple[str, ...] = ("bare_metal", "vm", "container", "unknown")


@dataclass
class HostFacts:
    kind: HostKind
    confidence: float
    os_name: str
    os_release: str
    machine: str
    in_container: bool
    in_vm: bool
    container_runtime: str | None = None  # docker|podman|containerd|cri-o|unknown|None
    vm_hypervisor: str | None = None
    cgroup_path: str | None = None
    evidence: list[str] = field(default_factory=list)
    deploy_profile_hint: str = "bare_metal"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def host_kind_label(kind: str) -> str:
    return {
        "bare_metal": "Bare metal",
        "vm": "Virtual machine",
        "container": "Container",
        "unknown": "Unknown host",
    }.get(kind, kind)


def _read_text(path: Path, limit: int = 65536) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return None


def _detect_container() -> tuple[bool, str | None, list[str]]:
    evidence: list[str] = []
    runtime: str | None = None

    # Explicit env (common across Docker/Podman/K8s)
    for key in (
        "ORGANISM_FORCE_HOST_KIND",
        "container",
        "CONTAINER",
        "KUBERNETES_SERVICE_HOST",
        "PODMAN_CONTAINER",
    ):
        if key == "ORGANISM_FORCE_HOST_KIND":
            continue
        if os.environ.get(key):
            evidence.append(f"env:{key}")
            if "PODMAN" in key.upper():
                runtime = "podman"
            elif "KUBERNETES" in key.upper():
                runtime = runtime or "containerd"
            else:
                runtime = runtime or "unknown"

    dockerenv = Path("/.dockerenv")
    if dockerenv.exists():
        evidence.append("/.dockerenv")
        runtime = runtime or "docker"

    # Podman often creates /run/.containerenv
    if Path("/run/.containerenv").exists():
        evidence.append("/run/.containerenv")
        runtime = "podman"

    cgroup = _read_text(Path("/proc/1/cgroup")) or ""
    if cgroup:
        if re.search(
            r"docker|containerd|kubepods|libpod|crio|podman|/pod-[a-z0-9]|pod.slice",
            cgroup,
            re.I,
        ):
            evidence.append("cgroup:container_marker")
            if "docker" in cgroup.lower():
                runtime = runtime or "docker"
            elif "libpod" in cgroup.lower() or "podman" in cgroup.lower():
                runtime = "podman"
            elif "crio" in cgroup.lower():
                runtime = "cri-o"
            elif "containerd" in cgroup.lower() or "kubepods" in cgroup.lower() or "/pod-" in cgroup.lower():
                runtime = runtime or "containerd"

    # PID 1 is often not init/systemd inside containers
    cmdline = _read_text(Path("/proc/1/cmdline")) or ""
    cmd = cmdline.replace("\x00", " ").strip()
    if cmd and not re.search(r"(systemd|init|launchd|wininit)", cmd, re.I):
        # weak signal — only count with other evidence
        if evidence:
            evidence.append(f"pid1:{cmd.split()[0] if cmd.split() else cmd[:40]}")

    # cgroup namespace hint via /proc/self/cgroup mountinfo
    mountinfo = _read_text(Path("/proc/self/mountinfo")) or ""
    if "/docker/" in mountinfo or "/containers/" in mountinfo:
        evidence.append("mountinfo:container_path")
        runtime = runtime or "unknown"

    in_container = bool(evidence)
    return in_container, runtime, evidence


def _detect_vm() -> tuple[bool, str | None, list[str]]:
    evidence: list[str] = []
    hypervisor: str | None = None
    sys_vendor = (_read_text(Path("/sys/class/dmi/id/sys_vendor")) or "").strip().lower()
    product = (_read_text(Path("/sys/class/dmi/id/product_name")) or "").strip().lower()
    bios = (_read_text(Path("/sys/class/dmi/id/bios_vendor")) or "").strip().lower()

    vm_markers = {
        "vmware": "vmware",
        "virtualbox": "virtualbox",
        "qemu": "qemu",
        "kvm": "kvm",
        "xen": "xen",
        "microsoft corporation": "hyper-v",
        "hyper-v": "hyper-v",
        "amazon ec2": "aws-nitro",
        "google": "gce",
        "openstack": "openstack",
        "parallels": "parallels",
        "bochs": "bochs",
        "bhyve": "bhyve",
    }
    blob = f"{sys_vendor} {product} {bios}"
    for needle, name in vm_markers.items():
        if needle in blob:
            evidence.append(f"dmi:{needle}")
            hypervisor = name
            break

    # CPU hypervisor flag (Linux)
    cpuinfo = _read_text(Path("/proc/cpuinfo")) or ""
    if "hypervisor" in cpuinfo.lower():
        evidence.append("cpuinfo:hypervisor")
        hypervisor = hypervisor or "unknown"

    # systemd-detect-virt style via /sys/devices/virtual/dmi — already covered
    # macOS: check sysctl hw.model for Virtual
    if platform.system() == "Darwin":
        try:
            import subprocess

            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.features"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            if "VMM" in out.upper() or "HYPERVISOR" in out.upper():
                evidence.append("sysctl:vmm")
                hypervisor = hypervisor or "unknown"
        except Exception:
            pass
        try:
            model = subprocess.check_output(
                ["sysctl", "-n", "hw.model"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=2,
            ).strip().lower()
            if any(x in model for x in ("virtual", "vmware", "parallels", "qemu")):
                evidence.append(f"hw.model:{model}")
                hypervisor = hypervisor or "unknown"
        except Exception:
            pass

    return bool(evidence), hypervisor, evidence


def detect_host(*, force_kind: str | None = None) -> HostFacts:
    """Return HostFacts for the current process environment.

    ``ORGANISM_FORCE_HOST_KIND`` or ``force_kind`` overrides detection
    (values: bare_metal|vm|container|unknown).
    """
    forced = (force_kind or os.environ.get("ORGANISM_FORCE_HOST_KIND") or "").strip().lower()
    os_name = platform.system()
    os_release = platform.release()
    machine = platform.machine()

    if forced in HOST_KINDS:
        hint = {
            "bare_metal": "bare_metal",
            "vm": "vm",
            "container": "container_generic",
            "unknown": "bare_metal",
        }[forced]
        return HostFacts(
            kind=forced,  # type: ignore[arg-type]
            confidence=1.0,
            os_name=os_name,
            os_release=os_release,
            machine=machine,
            in_container=forced == "container",
            in_vm=forced == "vm",
            evidence=[f"forced:{forced}"],
            deploy_profile_hint=hint,
        )

    in_container, runtime, c_ev = _detect_container()
    in_vm, hypervisor, v_ev = _detect_vm()
    evidence = list(c_ev) + list(v_ev)
    cgroup = _read_text(Path("/proc/1/cgroup"))

    # Priority: container > vm > bare
    if in_container:
        kind: HostKind = "container"
        confidence = 0.9 if len(c_ev) >= 2 else 0.7
        hint = "container_generic"
    elif in_vm:
        kind = "vm"
        confidence = 0.85 if hypervisor and hypervisor != "unknown" else 0.65
        hint = "vm"
    else:
        kind = "bare_metal"
        confidence = 0.75 if os_name == "Linux" else 0.55
        hint = "bare_metal"
        evidence.append("no_container_or_vm_markers")

    return HostFacts(
        kind=kind,
        confidence=confidence,
        os_name=os_name,
        os_release=os_release,
        machine=machine,
        in_container=in_container,
        in_vm=in_vm and not in_container,
        container_runtime=runtime if in_container else None,
        vm_hypervisor=hypervisor if in_vm and not in_container else None,
        cgroup_path=(cgroup.splitlines()[0] if cgroup else None),
        evidence=evidence,
        deploy_profile_hint=hint,
    )
