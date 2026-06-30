#!/usr/bin/env bash
# Optional: syncs the SRD reference corpus in from a remote host, for setups
# that keep a canonical reference dataset off-repo (e.g. a NAS or second
# machine). Not needed for a single-machine setup — the repo's own
# reference/open5e and reference/srd already carry a usable copy.
#
# Configure via env vars (no defaults baked in — there's no host to assume):
#   BIZZAL_REFERENCE_SOURCE_HOST, BIZZAL_REFERENCE_SOURCE_USER, BIZZAL_REFERENCE_SOURCE_PATH
# or pass them positionally: sync_reference.sh <host> <user> <path>
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SNAP_ROOT="$REPO_ROOT/reference/snapshots"
LEGACY_MIRROR_DIR="$REPO_ROOT/reference/srd5.1"
ACTIVE_LINK="$REPO_ROOT/reference/active"

HOST="${1:-${BIZZAL_REFERENCE_SOURCE_HOST:-}}"
USER="${2:-${BIZZAL_REFERENCE_SOURCE_USER:-}}"
SRC_PATH="${3:-${BIZZAL_REFERENCE_SOURCE_PATH:-}}"

if [[ -z "$HOST" || -z "$USER" || -z "$SRC_PATH" ]]; then
  echo "[sync_ref] No remote reference source configured." >&2
  echo "[sync_ref] Set BIZZAL_REFERENCE_SOURCE_HOST / _USER / _PATH, or pass host user path as args." >&2
  echo "[sync_ref] Skipping — this is optional for single-machine setups." >&2
  exit 0
fi

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
