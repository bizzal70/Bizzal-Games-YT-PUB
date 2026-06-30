#!/usr/bin/env bash
# Generic replacement for dnd_env.sh / shadowdark_env.sh. Sets BIZZAL_SYSTEM_ID
# plus all the path/feature-flag env vars for a given rpg_systems.id, deriving
# paths by convention from path_suffix (looked up from the DB) instead of
# hardcoding a new wrapper script per system.
#
# Usage: source bin/core/system_env.sh <system_id>
set -euo pipefail

SYSTEM_ID="${1:?Usage: system_env.sh <system_id>}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

export BIZZAL_SYSTEM_ID="$SYSTEM_ID"

# Look up path_suffix and chain_tag from the DB. This is the only DB round
# trip needed before the rest of the pipeline (which reads system_config.py
# directly) takes over.
read -r BIZZAL_CHAIN_TAG BIZZAL_PATH_SUFFIX < <(python3 - "$SYSTEM_ID" <<'PYEOF'
import sys
sys.path.insert(0, "bin/core")
import system_config
row = system_config.get_system(sys.argv[1])
print(row["chain_tag"], row["path_suffix"] or "__NONE__")
PYEOF
)
export BIZZAL_CHAIN_LABEL="$SYSTEM_ID"
export BIZZAL_CHAIN_TAG
[ "$BIZZAL_PATH_SUFFIX" = "__NONE__" ] && BIZZAL_PATH_SUFFIX=""
SFX="$BIZZAL_PATH_SUFFIX"

export BIZZAL_STYLE_HISTORY_PATH="runtime/state/style_history_${SYSTEM_ID}.json"

export BIZZAL_ATOM_INCOMING_DIR="data/atoms${SFX}/incoming"
export BIZZAL_ATOM_VALIDATED_DIR="data/atoms${SFX}/validated"
export BIZZAL_ATOM_FAILED_DIR="data/atoms${SFX}/failed"

export BIZZAL_RENDERS_BY_DAY_DIR="data/renders${SFX}/by_day"
export BIZZAL_RENDERS_LATEST_DIR="data/renders${SFX}/latest"
export BIZZAL_RENDERS_TMP_DIR="data/renders${SFX}/tmp"
export BIZZAL_LATEST_VIDEO_PATH="data/renders${SFX}/latest/latest.mp4"

export BIZZAL_DISCORD_APPROVAL_STATE="data/archive/approvals/discord_publish_gate${SFX}.json"
export BIZZAL_PUBLISH_REGISTRY="data/archive/publish/published_registry${SFX}.json"
export BIZZAL_PUBLISH_CMD="${BIZZAL_PUBLISH_CMD:-$REPO_ROOT/bin/upload/upload_youtube.py}"

# Monthly paths historically used a system_id suffix even for the "default"
# (unsuffixed) daily system, so they don't follow path_suffix -- they're
# always suffixed by the bare system_id.
export BIZZAL_DISCORD_MONTHLY_APPROVAL_STATE="data/archive/approvals/discord_monthly_publish_gate_${SYSTEM_ID}.json"
export BIZZAL_MONTHLY_PUBLISH_REGISTRY="data/archive/publish/published_monthly_registry_${SYSTEM_ID}.json"
export BIZZAL_MONTHLY_ROOT="data/archive/monthly/${SYSTEM_ID}"

# Feature-flag / prompt defaults come from the DB row too, but env vars (if
# already set by the caller, e.g. via ~/.config/bizzal.env) win.
eval "$(python3 - "$SYSTEM_ID" <<'PYEOF'
import sys
sys.path.insert(0, "bin/core")
import system_config
row = system_config.get_system(sys.argv[1])
def shq(s):
    return "'" + str(s or "").replace("'", "'\\''") + "'"
print(f"export BIZZAL_ENABLE_AI=${{BIZZAL_ENABLE_AI:-{1 if row['enable_ai'] else 0}}}")
print(f"export BIZZAL_ENABLE_AI_SCRIPT=${{BIZZAL_ENABLE_AI_SCRIPT:-{1 if row['enable_ai_script'] else 0}}}")
print(f"export BIZZAL_ENABLE_TTS=${{BIZZAL_ENABLE_TTS:-{1 if row['enable_tts'] else 0}}}")
print(f"export BIZZAL_ENABLE_BG_IMAGE=${{BIZZAL_ENABLE_BG_IMAGE:-{1 if row['enable_bg_image'] else 0}}}")
print(f"export BIZZAL_ENABLE_BG_MUSIC=${{BIZZAL_ENABLE_BG_MUSIC:-{1 if row['enable_bg_music'] else 0}}}")
print(f"export BIZZAL_ENABLE_PDF_FLAVOR=${{BIZZAL_ENABLE_PDF_FLAVOR:-{1 if row['enable_pdf_flavor'] else 0}}}")
print(f"export BIZZAL_TTS_VOICE_VARIETY_LOOKBACK_DAYS=${{BIZZAL_TTS_VOICE_VARIETY_LOOKBACK_DAYS:-{row['tts_voice_variety_lookback_days']}}}")
print(f"export BIZZAL_BG_IMAGE_PROMPT_PREFIX=${{BIZZAL_BG_IMAGE_PROMPT_PREFIX:-{shq(row['bg_image_prompt_prefix'])}}}")
print(f"export BIZZAL_BG_IMAGE_PROMPT_SUFFIX=${{BIZZAL_BG_IMAGE_PROMPT_SUFFIX:-{shq(row['bg_image_prompt_suffix'])}}}")
print(f"export BIZZAL_MUSIC_PROMPT_PREFIX=${{BIZZAL_MUSIC_PROMPT_PREFIX:-{shq(row['music_prompt_prefix'])}}}")
print(f"export BIZZAL_MUSIC_PROMPT_SUFFIX=${{BIZZAL_MUSIC_PROMPT_SUFFIX:-{shq(row['music_prompt_suffix'])}}}")
PYEOF
)"

mkdir -p \
  "$REPO_ROOT/$BIZZAL_ATOM_INCOMING_DIR" \
  "$REPO_ROOT/$BIZZAL_ATOM_VALIDATED_DIR" \
  "$REPO_ROOT/$BIZZAL_ATOM_FAILED_DIR" \
  "$REPO_ROOT/$BIZZAL_RENDERS_BY_DAY_DIR" \
  "$REPO_ROOT/$BIZZAL_RENDERS_LATEST_DIR" \
  "$REPO_ROOT/$BIZZAL_RENDERS_TMP_DIR" \
  "$REPO_ROOT/logs/$SYSTEM_ID" \
  "$REPO_ROOT/data/archive/approvals" \
  "$REPO_ROOT/data/archive/publish"
