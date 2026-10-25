# Organism single-device deploy (CPU-only)

Run Organism on **any hardware** with no GPU and no Hybrid checkout required.

## N-step quickstart (host)

```bash
# 1. Clone / enter repo
cd /path/to/organism

# 2. venv + install
python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# 3. Validate profile
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk \
  validate-config -c deploy/config/cpu_only.yaml

# 4. Dry-run (builds stack, no bind)
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk \
  serve -c deploy/config/cpu_only.yaml --dry-run

# 5. Serve health/status
PYTHONPATH=sdk/python:modules:. .venv/bin/python -m organism_sdk \
  serve -c deploy/config/cpu_only.yaml
# → http://127.0.0.1:8787/health  and  /status
```

Or: `./deploy/entrypoint.sh --dry-run`

## Docker

```bash
docker build -f deploy/Dockerfile -t organism:cpu .
docker run --rm -p 8787:8787 organism:cpu
```

## systemd

Copy `deploy/systemd/organism.service` to `/etc/systemd/system/`, install the
tree under `/opt/organism`, config under `/etc/organism/cpu_only.yaml`, then:

```bash
systemctl enable --now organism
```

## Env

See `deploy/config/cpu_only.env.example`. CPU is always the minimum; set
`ORGANISM_PREFER_GPU=1` only to soft-prefer CUDA when present.
