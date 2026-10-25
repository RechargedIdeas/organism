# Organism deploy — bare metal first, Docker optional

Organism runs **100% bare metal**, inside **any VM**, and inside **any container
system**. **Docker is not required** and is never the only path.

| Profile | Config | Host |
|---|---|---|
| `bare_metal` | `deploy/config/bare_metal.yaml` | Physical host (first-class) |
| `vm` | `deploy/config/vm.yaml` | Any hypervisor / cloud VM |
| `container_generic` | `deploy/config/container_generic.yaml` | Docker **or** Podman **or** CRI-O / containerd |
| `cpu_only` | `deploy/config/cpu_only.yaml` | Alias of bare-metal CPU defaults |

`organism status` reports `host_kind` (`bare_metal`|`vm`|`container`) without
assuming Docker. Override with `ORGANISM_FORCE_HOST_KIND`.

## N-step quickstart (bare metal / VM — preferred)

```bash
cd /path/to/organism
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk \
  validate-config -c deploy/config/bare_metal.yaml

PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk \
  serve -c deploy/config/bare_metal.yaml --dry-run

PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk status
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk sandbox self-check
```

Or: `./deploy/entrypoint.sh --dry-run`

### systemd (bare / VM)

```bash
sudo ./deploy/bare/install.sh /opt/organism
sudo systemctl start organism
```

Unit: `deploy/systemd/organism.service` (NoNewPrivileges, ProtectSystem, MemoryMax).

## Container (optional)

Docker is **one** optional backend under `container_generic`. Prefer the
Docker-and-Podman-friendly Containerfile:

```bash
# Podman (rootless OK)
podman build -f deploy/container/Containerfile -t organism:cpu .
podman run --rm -p 8787:8787 organism:cpu

# Docker (optional)
docker build -f deploy/container/Containerfile -t organism:cpu .
# or: docker build -f deploy/Dockerfile -t organism:cpu .
```

CRI-O / containerd: build the same OCI image and run under your runtime; no
Organism code path hard-depends on the Docker CLI or daemon.

## Native sandbox

Organism ships a **custom integrated sandbox** (`organism_sdk.sandbox`):

```bash
organism sandbox status
organism sandbox self-check
organism sandbox run -- python -c "print('jailed')"
```

See [docs/v1.10/BARE_METAL_AND_SANDBOX.md](../docs/v1.10/BARE_METAL_AND_SANDBOX.md).

## Env

See `deploy/config/cpu_only.env.example`. CPU is always the minimum; set
`ORGANISM_PREFER_GPU=1` only to soft-prefer CUDA when present.
