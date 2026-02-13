#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SNAP_ROOT="$REPO_ROOT/reference/snapshots"
LEGACY_MIRROR_DIR="$REPO_ROOT/reference/srd5.1"
ACTIVE_LINK="$REPO_ROOT/reference/active"

HOST="${1:-192.168.68.128}"
USER="${2:-umbrel}"
SRC_PATH="${3:-/home/umbrel/umbrel/data/reference/open5e/ACTIVE_WOTC_SRD}"
STAMP="$(date +%Y%m%d_%H%M%S)"
SNAP_DIR="$SNAP_ROOT/srd_2024_${STAMP}"

echo "[sync_ref] repo=$REPO_ROOT"
echo "[sync_ref] source=${USER}@${HOST}:${SRC_PATH}/"
echo "[sync_ref] snapshot=$SNAP_DIR"
echo "[sync_ref] active_link=$ACTIVE_LINK"
echo "[sync_ref] legacy_mirror=$LEGACY_MIRROR_DIR"

mkdir -p "$SNAP_DIR"
mkdir -p "$LEGACY_MIRROR_DIR"
mkdir -p "$SNAP_ROOT"

rsync -av --delete \
  "${USER}@${HOST}:${SRC_PATH}/" \
  "$SNAP_DIR/"

ln -sfn "$SNAP_DIR" "$ACTIVE_LINK"

# Backward-compatible mirror for older defaults/tools.
if [[ -L "$LEGACY_MIRROR_DIR" ]]; then
  LEGACY_TARGET="$(readlink -f "$LEGACY_MIRROR_DIR" || true)"
  echo "[sync_ref] NOTE: legacy mirror path is a symlink: $LEGACY_MIRROR_DIR -> $LEGACY_TARGET"
  echo "[sync_ref] NOTE: skipping destructive legacy mirror rsync to avoid mutating external path"
  echo "[sync_ref] NOTE: using reference/active as canonical dataset"
else
  rsync -a --delete "$ACTIVE_LINK/" "$LEGACY_MIRROR_DIR/"
fi

echo "[sync_ref] building inventory..."
python3 "$REPO_ROOT/bin/core/inventory_active_srd.py"

echo "[sync_ref] done"
