#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

BACKUP_ROOT="docs/ops_backups"
KEEP="12"
DRY_RUN="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-root)
      BACKUP_ROOT="${2:-$BACKUP_ROOT}"
      shift 2
      ;;
    --keep)
      KEEP="${2:-$KEEP}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    *)
      echo "usage: bin/core/prune_ops_backups.sh [--backup-root PATH] [--keep N] [--dry-run]" >&2
      exit 2
      ;;
  esac
done

if [[ "$BACKUP_ROOT" != /* ]]; then
  BACKUP_ROOT="$REPO_ROOT/$BACKUP_ROOT"
fi

if ! [[ "$KEEP" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --keep must be an integer >= 0" >&2
  exit 2
fi

if [[ ! -d "$BACKUP_ROOT" ]]; then
  echo "[prune_ops_backups] backup root missing, nothing to do: $BACKUP_ROOT"
  exit 0
fi

mapfile -t DIRS < <(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r)
TOTAL="${#DIRS[@]}"

echo "[prune_ops_backups] root=$BACKUP_ROOT"
echo "[prune_ops_backups] total=$TOTAL keep=$KEEP dry_run=$DRY_RUN"

if (( TOTAL <= KEEP )); then
  echo "[prune_ops_backups] nothing to prune"
  exit 0
fi

PRUNE_COUNT=$(( TOTAL - KEEP ))
for (( i=KEEP; i<TOTAL; i++ )); do
  target="$BACKUP_ROOT/${DIRS[$i]}"
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[prune_ops_backups] would_remove=$target"
  else
    rm -rf "$target"
    echo "[prune_ops_backups] removed=$target"
  fi
done

echo "[prune_ops_backups] pruned=$PRUNE_COUNT"
