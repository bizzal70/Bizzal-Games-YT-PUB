#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

MONTH="${1:-$(date +%Y-%m)}"
MONTHLY_ROOT="${BIZZAL_MONTHLY_ROOT:-data/archive/monthly}"
RENDERS_DIR="${BIZZAL_RENDERS_BY_DAY_DIR:-data/renders/by_day}"
MONTH_DIR="${MONTHLY_ROOT%/}/${MONTH}"
MANIFEST_JSON="${MONTH_DIR}/manifest.json"
CONCAT_LIST="${MONTH_DIR}/longform.concat.txt"
OUT_MP4="${MONTH_DIR}/monthly_longform_${MONTH}.mp4"
REPORT_JSON="${MONTH_DIR}/monthly_longform_${MONTH}.json"
APPROVAL_STATE="${BIZZAL_DISCORD_APPROVAL_STATE:-data/archive/approvals/discord_publish_gate.json}"
REQUIRE_APPROVAL="${BIZZAL_MONTHLY_REQUIRE_DISCORD_APPROVAL:-1}"
INCLUDED_DAYS_FILE="${MONTH_DIR}/monthly_longform.included_days.txt"
MISSING_DAYS_FILE="${MONTH_DIR}/monthly_longform.missing_days.txt"
UNAPPROVED_DAYS_FILE="${MONTH_DIR}/monthly_longform.unapproved_days.txt"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[monthly_concat] ERROR: ffmpeg not found in PATH" >&2
  exit 2
fi

if [[ ! "$MONTH" =~ ^[0-9]{4}-[0-9]{2}$ ]]; then
  echo "[monthly_concat] ERROR: month must be YYYY-MM" >&2
  exit 2
fi

mkdir -p "$MONTH_DIR"

declare -a DAYS=()
declare -a INPUTS=()
declare -a MISSING=()
declare -a UNAPPROVED=()

if [[ -f "$MANIFEST_JSON" ]]; then
  while IFS= read -r day; do
    [[ -n "$day" ]] && DAYS+=("$day")
  done < <(jq -r '.entries[]?.day // empty' "$MANIFEST_JSON")
else
  while IFS= read -r p; do
    day="$(basename "$p" .mp4)"
    [[ -n "$day" ]] && DAYS+=("$day")
  done < <(find "$RENDERS_DIR" -maxdepth 1 -type f -name "${MONTH}-*.mp4" | sort)
fi

if (( ${#DAYS[@]} == 0 )); then
  echo "[monthly_concat] ERROR: no days found for month=${MONTH}" >&2
  exit 3
fi

if [[ "$REQUIRE_APPROVAL" == "1" && ! -f "$APPROVAL_STATE" ]]; then
  echo "[monthly_concat] ERROR: approval state missing while approval filter enabled: $APPROVAL_STATE" >&2
  exit 5
fi

for day in "${DAYS[@]}"; do
  src="${RENDERS_DIR}/${day}.mp4"
  if [[ ! -f "$src" ]]; then
    MISSING+=("$day")
    continue
  fi

  if [[ "$REQUIRE_APPROVAL" == "1" ]]; then
    status="$(jq -r --arg day "$day" '.approvals[$day].status // ""' "$APPROVAL_STATE" 2>/dev/null || echo "")"
    case "$status" in
      approved|published)
        INPUTS+=("$(realpath "$src")")
        ;;
      *)
        UNAPPROVED+=("${day}:${status:-missing}")
        ;;
    esac
  else
    INPUTS+=("$(realpath "$src")")
  fi
done

if (( ${#INPUTS[@]} == 0 )); then
  if [[ "$REQUIRE_APPROVAL" == "1" ]]; then
    echo "[monthly_concat] ERROR: no approved render files found for month=${MONTH}" >&2
  else
    echo "[monthly_concat] ERROR: no render files found for month=${MONTH}" >&2
  fi
  exit 4
fi

: > "$INCLUDED_DAYS_FILE"
for src in "${INPUTS[@]}"; do
  basename "$src" .mp4 >> "$INCLUDED_DAYS_FILE"
done

: > "$MISSING_DAYS_FILE"
for day in "${MISSING[@]}"; do
  echo "$day" >> "$MISSING_DAYS_FILE"
done

: > "$UNAPPROVED_DAYS_FILE"
for day_status in "${UNAPPROVED[@]}"; do
  echo "$day_status" >> "$UNAPPROVED_DAYS_FILE"
done

: > "$CONCAT_LIST"
for src in "${INPUTS[@]}"; do
  esc="${src//\'/\'\\\'\'}"
  printf "file '%s'\n" "$esc" >> "$CONCAT_LIST"
done

CRF="${BIZZAL_MONTHLY_CRF:-20}"
PRESET="${BIZZAL_MONTHLY_PRESET:-medium}"

echo "[monthly_concat] month=${MONTH}" >&2
echo "[monthly_concat] inputs=${#INPUTS[@]} missing=${#MISSING[@]} unapproved=${#UNAPPROVED[@]} require_approval=${REQUIRE_APPROVAL}" >&2
echo "[monthly_concat] writing=${OUT_MP4}" >&2

ffmpeg -y -hide_banner -loglevel error \
  -f concat -safe 0 -i "$CONCAT_LIST" \
  -c:v libx264 -preset "$PRESET" -crf "$CRF" -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 192k -ac 2 -ar 48000 \
  -movflags +faststart \
  "$OUT_MP4"

OUT_SIZE_BYTES="$(stat -c%s "$OUT_MP4" 2>/dev/null || echo 0)"
if command -v ffprobe >/dev/null 2>&1; then
  OUT_DURATION_SEC="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$OUT_MP4" 2>/dev/null || echo 0)"
else
  OUT_DURATION_SEC="0"
fi
OUT_DURATION_SEC_1DP="$(python3 - <<'PY' "$OUT_DURATION_SEC"
import sys
try:
    v = float(sys.argv[1])
except Exception:
    v = 0.0
print(f"{v:.1f}")
PY
)"
OUT_DURATION_HMS="$(python3 - <<'PY' "$OUT_DURATION_SEC"
import sys
try:
    total = max(0, int(round(float(sys.argv[1]))))
except Exception:
    total = 0
h = total // 3600
m = (total % 3600) // 60
s = total % 60
print(f"{h:02d}:{m:02d}:{s:02d}")
PY
)"
OUT_SIZE_MB="$(python3 - <<'PY' "$OUT_SIZE_BYTES"
import sys
size = int(sys.argv[1]) if sys.argv[1].isdigit() else 0
print(f"{size / (1024 * 1024):.2f}")
PY
)"

python3 - "$REPORT_JSON" "$MONTH" "$OUT_MP4" "${#INPUTS[@]}" "${#MISSING[@]}" "$OUT_SIZE_BYTES" "$OUT_DURATION_SEC" "$REQUIRE_APPROVAL" "$INCLUDED_DAYS_FILE" "$MISSING_DAYS_FILE" "$UNAPPROVED_DAYS_FILE" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone

report_path, month, out_mp4, inputs_count, missing_count, size_bytes, duration_sec, require_approval, included_days_file, missing_days_file, unapproved_days_file = sys.argv[1:12]


def read_lines(path: str):
  if not path or not os.path.exists(path):
    return []
  with open(path, "r", encoding="utf-8") as f:
    return [line.strip() for line in f if line.strip()]


payload = {
    "month": month,
    "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "output": out_mp4,
    "output_size_bytes": int(size_bytes) if str(size_bytes).isdigit() else (os.path.getsize(out_mp4) if os.path.exists(out_mp4) else 0),
    "output_duration_sec": float(duration_sec) if str(duration_sec).strip() else 0.0,
    "output_duration_hms": "00:00:00",
    "inputs_count": int(inputs_count),
    "missing_count": int(missing_count),
  "require_discord_approval": require_approval == "1",
  "included_days": read_lines(included_days_file),
  "missing_days": read_lines(missing_days_file),
  "unapproved_days": read_lines(unapproved_days_file),
}
secs = payload["output_duration_sec"]
total = max(0, int(round(secs)))
payload["output_duration_hms"] = f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY

if (( ${#MISSING[@]} > 0 )); then
  echo "[monthly_concat] WARNING: missing days: ${MISSING[*]}" >&2
fi
if (( ${#UNAPPROVED[@]} > 0 )); then
  echo "[monthly_concat] WARNING: unapproved days skipped: ${UNAPPROVED[*]}" >&2
fi

echo "[monthly_concat] summary duration_sec=${OUT_DURATION_SEC_1DP} duration_hms=${OUT_DURATION_HMS} size_mb=${OUT_SIZE_MB} inputs=${#INPUTS[@]} missing=${#MISSING[@]} unapproved=${#UNAPPROVED[@]} require_approval=${REQUIRE_APPROVAL}" >&2
echo "[monthly_concat] wrote: ${OUT_MP4}" >&2
echo "[monthly_concat] wrote: ${REPORT_JSON}" >&2
