# Organism v1.10 — Bare metal first + native sandbox

**Date:** 2026-10-25 (America/New_York)  
**Release:** v1.10.0  
**Constraints:** Organism naming · bio `may_actuate=False` · no Hybrid Studio · CPU Everywhere · **Docker not required**

## Goals

1. Run **100% bare metal**, inside **any VM**, and inside **any container system**.
2. Never rely on Docker; containers are an optional backend under `container_generic`.
3. Ship a **custom, natively built and integrated sandbox** so Organism can
   self-contain itself and all child processes effectively.

## A. Host portability

### Deploy profiles

| Profile | File | Notes |
|---|---|---|
| `bare_metal` | `deploy/config/bare_metal.yaml` | First-class physical host |
| `vm` | `deploy/config/vm.yaml` | Any hypervisor / cloud VM |
| `container_generic` | `deploy/config/container_generic.yaml` | Docker **or** Podman **or** CRI-O |
| `cpu_only` | `deploy/config/cpu_only.yaml` | Alias of bare-metal CPU defaults |

### Detection

`organism_sdk.host.detect_host()` inspects `/.dockerenv`, `/run/.containerenv`,
cgroup markers, DMI/CPU hypervisor flags. Override with
`ORGANISM_FORCE_HOST_KIND=bare_metal|vm|container|unknown`.

`organism status` (and Desktop Ops) always include:

- `host_kind`, `host` (full facts)
- `docker_required: false`
- `sandbox` (native capabilities + policies)

### Install paths

```bash
# Bare / VM (preferred)
sudo ./deploy/bare/install.sh /opt/organism
sudo systemctl enable --now organism

# venv only (no root, no Docker)
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk \
  serve -c deploy/config/bare_metal.yaml
```

### Containers (optional)

```bash
podman build -f deploy/container/Containerfile -t organism:cpu .
# or: docker build -f deploy/container/Containerfile -t organism:cpu .
```

`deploy/Dockerfile` remains an **example** only. CI Docker/OCI jobs are
`continue-on-error` and never block required gates
(`.github/workflows/ci.yml` → `docker_optional`,
`.github/workflows/container-optional.yml`).

## B. Native Organism Sandbox

Module: `organism_sdk.sandbox`

| Piece | Role |
|---|---|
| `SandboxPolicy` | CPU / RSS / time / fds / nproc / network allowlist / ns flags |
| `ProcessJail` | subprocess + rlimits + optional Linux `unshare` (user/mount[/pid/net]) |
| `OrganismSandbox` | status / run / wrap_self / self_check / generative compose |
| `SandboxAuditLog` | ring buffer → `TraceEmitter.emit_sandbox` |

### Behavior

- **Linux:** rlimits + best-effort namespaces; degrade when caps missing.
- **macOS / Windows / restricted VMs / nested containers:** rlimits when
  available; namespaces marked degraded; spawn + shell-escape refuse still work.
- **Self-sandbox:** `wrap_self` / `SandboxPolicy.self_containment()` for worker
  pool, generative, soak, federation children.
- **Generative:** existing `SafeSandbox` (AST) composes via
  `run_under_organism_jail` / `OrganismSandbox.run_generative_source`.
- **CPU Everywhere:** no GPU hard-dep. **Docker never required.**

### CLI

```bash
organism sandbox status
organism sandbox self-check
organism sandbox run -- python -c "print('jailed')"
organism sandbox run --self-sandbox -- ./scripts/soak_target.sh
```

### Desktop

Ops panel: host badge, sandbox badge, **Sandbox self-check** button.

### Safety

- Shell escape (`/bin/sh`, bash, powershell as argv0; `-c` + `os.system` patterns) refused.
- Env scrub of cloud/LLM key prefixes inside jail.
- Bio `may_actuate` never set by sandbox policy.
- Audit events are first-class traces (`SandboxTraceEntry`).

## Gates

- `v110:bare_sandbox` — `sdk/python/tests/test_v110_bare_sandbox.py`
- `v110:desktop_ops_sandbox` — `desktop/tests/test_v110_ops_sandbox.py`

## Non-goals (unchanged)

Real neuromorphic silicon, wet-lab GPIO actuation, production WAN BFT+TPM,
Hybrid Studio UI, hosted LLM provider account.
