#!/usr/bin/env bash
# Archive a day's rendered MP4 to a Supabase Storage bucket so there's an
# off-YouTube copy + a URL for spot-checking. This is deliberately NON-FATAL:
# publishing has already happened by the time this runs, so a storage hiccup
# must never fail the pipeline.
#
# Usage: archive_render_to_storage.sh <system_id> [day]
#
# Requires:
#   SUPABASE_SERVICE_ROLE_KEY  - service-role key (bypasses Storage RLS)
#   SUPABASE_URL               - e.g. https://<ref>.supabase.co
#                                (defaults to the bizzal_Game_Pub project)
#   BIZZAL_STORAGE_BUCKET      - bucket name (default: renders)
set -u

SYSTEM_ID="${1:?Usage: archive_render_to_storage.sh <system_id> [day]}"
DAY="${2:-$(date +%F)}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT" || exit 0

SUPABASE_URL="${SUPABASE_URL:-https://nlywxefvpibkqfctgmty.supabase.co}"
BUCKET="${BIZZAL_STORAGE_BUCKET:-renders}"
KEY="${SUPABASE_SERVICE_ROLE_KEY:-}"

if [[ -z "$KEY" ]]; then
  echo "[archive_render] SKIP: SUPABASE_SERVICE_ROLE_KEY not set"
  exit 0
fi

# Resolve path_suffix to find the render. Mirrors system_env.sh convention.
SFX="$(python3 - "$SYSTEM_ID" <<'PYEOF' 2>/dev/null || true
import sys
sys.path.insert(0, "bin/core")
import system_config
print(system_config.get_system(sys.argv[1])["path_suffix"] or "")
PYEOF
)"

CANDIDATES=(
  "data/renders${SFX}/by_day/${DAY}.mp4"
  "data/renders${SFX}/by_day/${DAY}/final.mp4"
  "data/renders${SFX}/latest/latest.mp4"
)

SRC=""
for c in "${CANDIDATES[@]}"; do
  if [[ -f "$REPO_ROOT/$c" ]]; then SRC="$REPO_ROOT/$c"; break; fi
done

if [[ -z "$SRC" ]]; then
  echo "[archive_render] SKIP: no render found for $SYSTEM_ID day=$DAY (looked in: ${CANDIDATES[*]})"
  exit 0
fi

DEST="${SYSTEM_ID}/${DAY}.mp4"
URL="${SUPABASE_URL%/}/storage/v1/object/${BUCKET}/${DEST}"

echo "[archive_render] uploading $SRC -> ${BUCKET}/${DEST}"
http_code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$URL" \
  -H "Authorization: Bearer ${KEY}" \
  -H "apikey: ${KEY}" \
  -H "x-upsert: true" \
  -H "Content-Type: video/mp4" \
  --data-binary "@${SRC}" || echo "000")"

if [[ "$http_code" =~ ^2 ]]; then
  echo "[archive_render] OK (http=$http_code) ${BUCKET}/${DEST}"
else
  echo "[archive_render] WARN: upload returned http=$http_code (non-fatal)"
fi
exit 0
