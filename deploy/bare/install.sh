#!/usr/bin/env bash
# Organism bare-metal / VM installer — Docker NOT required.
# Usage: sudo ./deploy/bare/install.sh [/opt/organism]
set -euo pipefail

PREFIX="${1:-/opt/organism}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG_DIR="${ORGANISM_CONFIG_DIR:-/etc/organism}"
DATA_DIR="${ORGANISM_DATA_DIR:-/var/lib/organism}"
USER_NAME="${ORGANISM_USER:-organism}"
GROUP_NAME="${ORGANISM_GROUP:-organism}"
PYTHON_BIN="${ORGANISM_PYTHON:-python3}"

echo "==> Organism bare install"
echo "    repo:   $REPO_ROOT"
echo "    prefix: $PREFIX"
echo "    config: $CONFIG_DIR"
echo "    data:   $DATA_DIR"
echo "    docker: NOT required"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run as root (sudo) so systemd + /opt + /etc can be written." >&2
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python not found ($PYTHON_BIN). Install Python >= 3.11." >&2
  exit 1
fi

if ! id -u "$USER_NAME" >/dev/null 2>&1; then
  useradd --system --home-dir "$PREFIX" --shell /usr/sbin/nologin "$USER_NAME" || true
fi

mkdir -p "$PREFIX" "$CONFIG_DIR" "$DATA_DIR/artifacts" "$DATA_DIR/organisms"
# Sync tree (exclude venv/git/target)
rsync -a --delete \
  --exclude '.venv' --exclude '.git' --exclude 'target' --exclude '__pycache__' \
  --exclude 'organism_data' --exclude '.pytest_cache' \
  "$REPO_ROOT/" "$PREFIX/"

cd "$PREFIX"
"$PYTHON_BIN" -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e ".[dev]"

# Prefer bare_metal profile; fall back to cpu_only
if [[ -f deploy/config/bare_metal.yaml ]]; then
  cp -n deploy/config/bare_metal.yaml "$CONFIG_DIR/cpu_only.yaml" 2>/dev/null \
    || cp deploy/config/bare_metal.yaml "$CONFIG_DIR/organism.yaml"
  cp deploy/config/bare_metal.yaml "$CONFIG_DIR/bare_metal.yaml"
else
  cp deploy/config/cpu_only.yaml "$CONFIG_DIR/cpu_only.yaml"
fi
cp deploy/config/vm.yaml "$CONFIG_DIR/vm.yaml" 2>/dev/null || true
cp deploy/config/container_generic.yaml "$CONFIG_DIR/container_generic.yaml" 2>/dev/null || true

chown -R "$USER_NAME:$GROUP_NAME" "$PREFIX" "$DATA_DIR"
# Config readable by service user
chown -R "root:$GROUP_NAME" "$CONFIG_DIR"
chmod 0640 "$CONFIG_DIR"/*.yaml 2>/dev/null || true

UNIT_SRC="$PREFIX/deploy/systemd/organism.service"
UNIT_DST="/etc/systemd/system/organism.service"
sed "s|/opt/organism|$PREFIX|g" "$UNIT_SRC" > "$UNIT_DST"
# Point at bare_metal if present
if [[ -f "$CONFIG_DIR/bare_metal.yaml" ]]; then
  sed -i "s|ORGANISM_CONFIG=.*|ORGANISM_CONFIG=$CONFIG_DIR/bare_metal.yaml|" "$UNIT_DST" || true
fi

systemctl daemon-reload
systemctl enable organism.service

echo "==> Validating (no Docker)"
sudo -u "$USER_NAME" env \
  PYTHONPATH="$PREFIX/sdk/python:$PREFIX/modules:$PREFIX" \
  ORGANISM_CONFIG="$CONFIG_DIR/bare_metal.yaml" \
  "$PREFIX/.venv/bin/python" -m organism_sdk validate-config -c "$CONFIG_DIR/bare_metal.yaml"

sudo -u "$USER_NAME" env \
  PYTHONPATH="$PREFIX/sdk/python:$PREFIX/modules:$PREFIX" \
  "$PREFIX/.venv/bin/python" -m organism_sdk sandbox self-check || true

echo "==> Done. Start with: systemctl start organism"
echo "    Status: systemctl status organism"
echo "    CLI:    $PREFIX/.venv/bin/python -m organism_sdk status"
echo "    Host:   bare metal / VM first-class; Docker optional only."
