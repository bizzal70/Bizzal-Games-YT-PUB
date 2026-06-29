#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

MONTH="${1:-$(date +%Y-%m)}"
MONTHLY_ROOT="${BIZZAL_MONTHLY_ROOT:-data/archive/monthly}"
OUT_DIR="${MONTHLY_ROOT%/}/${MONTH}"

echo "[monthly_release] month=${MONTH}"
echo "[monthly_release] repo=${REPO_ROOT}"

echo "[monthly_release] generating manifest..."
bin/core/monthly_export_manifest.py --month "$MONTH"

echo "[monthly_release] generating zine pack..."
bin/core/monthly_export_pack.py --month "$MONTH"

echo "[monthly_release] generating long-form monthly video..."
bin/core/monthly_concat_video.sh "$MONTH"

MANIFEST_JSON="$OUT_DIR/manifest.json"
PACK_MD="$OUT_DIR/zine_pack/content.md"
PACK_CSV="$OUT_DIR/zine_pack/assets.csv"
LONGFORM_MP4="$OUT_DIR/monthly_longform_${MONTH}.mp4"
LONGFORM_JSON="$OUT_DIR/monthly_longform_${MONTH}.json"

if [[ ! -f "$MANIFEST_JSON" ]]; then
  echo "[monthly_release] ERROR: missing manifest: $MANIFEST_JSON" >&2
  exit 2
fi
if [[ ! -f "$PACK_MD" ]]; then
  echo "[monthly_release] ERROR: missing content pack: $PACK_MD" >&2
  exit 3
fi
if [[ ! -f "$PACK_CSV" ]]; then
  echo "[monthly_release] ERROR: missing assets pack: $PACK_CSV" >&2
  exit 4
fi
if [[ ! -f "$LONGFORM_MP4" ]]; then
  echo "[monthly_release] ERROR: missing long-form video: $LONGFORM_MP4" >&2
  exit 5
fi
if [[ ! -f "$LONGFORM_JSON" ]]; then
  echo "[monthly_release] ERROR: missing long-form report: $LONGFORM_JSON" >&2
  exit 6
fi

COUNT="$(jq -r '.count // 0' "$MANIFEST_JSON")"
BUNDLE_ID="$(jq -r '.month_bundle_id // "unknown"' "$MANIFEST_JSON")"

echo "[monthly_release] bundle_id=${BUNDLE_ID}"
echo "[monthly_release] entries=${COUNT}"

if [[ "$COUNT" == "0" ]]; then
  echo "[monthly_release] WARNING: manifest has zero entries" >&2
fi

echo "[monthly_release] wrote: $MANIFEST_JSON"
echo "[monthly_release] wrote: $PACK_MD"
echo "[monthly_release] wrote: $PACK_CSV"
echo "[monthly_release] wrote: $LONGFORM_MP4"
echo "[monthly_release] wrote: $LONGFORM_JSON"
echo "[monthly_release] DONE"
