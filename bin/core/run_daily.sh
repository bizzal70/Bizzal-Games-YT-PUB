#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"

DAY="$(date +%F)"
ATOM_VALID="data/atoms/validated/${DAY}.json"

echo "[run_daily] DAY=$DAY"
echo "[run_daily] repo=$REPO"

# 1) Make + validate atom
echo "[run_daily] make_atom..."
bin/core/make_atom.py

if [[ ! -f "$ATOM_VALID" ]]; then
  echo "[run_daily] ERROR: validated atom not found: $ATOM_VALID"
  exit 2
fi

# 2) Render video (you already have render pipeline stubs; use what exists)
# Prefer an existing script if present.
if [[ -x "bin/render/render_latest.sh" ]]; then
  echo "[run_daily] render_latest..."
  bin/render/render_latest.sh
elif [[ -x "bin/core/render_latest.sh" ]]; then
  echo "[run_daily] render_latest..."
  bin/core/render_latest.sh
elif [[ -x "bin/render/render_atom.sh" ]]; then
  echo "[run_daily] render_atom.sh..."
  bin/render/render_atom.sh "$DAY"
elif [[ -f "bin/render/render_atom.sh" ]]; then
  echo "[run_daily] render_atom.sh (via bash)..."
  bash bin/render/render_atom.sh "$DAY"
elif [[ -x "bin/render/render_atom.py" ]]; then
  echo "[run_daily] render_atom.py..."
  bin/render/render_atom.py "$ATOM_VALID"
else
  echo "[run_daily] NOTE: no render script found yet. Atom is validated and ready."
fi

# 3) Upload (optional): only run if a known upload script exists
if [[ -x "bin/upload/upload_youtube.py" ]]; then
  if [[ "${BIZZAL_REQUIRE_DISCORD_APPROVAL:-0}" == "1" ]]; then
    echo "[run_daily] upload gated: awaiting Discord approval (BIZZAL_REQUIRE_DISCORD_APPROVAL=1)"
  else
    echo "[run_daily] upload_youtube..."
    bin/upload/upload_youtube.py
  fi
else
  echo "[run_daily] NOTE: no upload script found yet."
fi

echo "[run_daily] DONE"
