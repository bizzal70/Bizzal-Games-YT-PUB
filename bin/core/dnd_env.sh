#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

export BIZZAL_CHAIN_LABEL="dnd"
export BIZZAL_CHAIN_TAG="D&D"

# Explicit D&D config and source paths to avoid cross-chain bleed.
export BIZZAL_REFERENCE_SOURCES_PATH="${BIZZAL_DND_REFERENCE_SOURCES_PATH:-config/reference_sources.yaml}"
export BIZZAL_TOPIC_SPINE_PATH="${BIZZAL_DND_TOPIC_SPINE_PATH:-config/topic_spine.yaml}"
export BIZZAL_STYLE_RULES_PATH="${BIZZAL_DND_STYLE_RULES_PATH:-config/style_rules.yaml}"
export BIZZAL_STYLE_HISTORY_PATH="${BIZZAL_DND_STYLE_HISTORY_PATH:-runtime/state/style_history_dnd.json}"

export BIZZAL_ACTIVE_SRD_PATH="${BIZZAL_DND_ACTIVE_SRD_PATH:-${BIZZAL_ACTIVE_SRD_PATH:-reference/active}}"
export BIZZAL_SRD_PDF_PATH="${BIZZAL_DND_SRD_PDF_PATH:-${BIZZAL_SRD_PDF_PATH:-reference/srd/SRD_CC_v5.2.1.pdf}}"

export BIZZAL_ATOM_INCOMING_DIR="${BIZZAL_DND_ATOM_INCOMING_DIR:-data/atoms/incoming}"
export BIZZAL_ATOM_VALIDATED_DIR="${BIZZAL_DND_ATOM_VALIDATED_DIR:-data/atoms/validated}"
export BIZZAL_ATOM_FAILED_DIR="${BIZZAL_DND_ATOM_FAILED_DIR:-data/atoms/failed}"

export BIZZAL_RENDERS_BY_DAY_DIR="${BIZZAL_DND_RENDERS_BY_DAY_DIR:-data/renders/by_day}"
export BIZZAL_RENDERS_LATEST_DIR="${BIZZAL_DND_RENDERS_LATEST_DIR:-data/renders/latest}"
export BIZZAL_RENDERS_TMP_DIR="${BIZZAL_DND_RENDERS_TMP_DIR:-data/renders/tmp}"
export BIZZAL_LATEST_VIDEO_PATH="${BIZZAL_DND_LATEST_VIDEO_PATH:-data/renders/latest/latest.mp4}"

export BIZZAL_DISCORD_APPROVAL_STATE="${BIZZAL_DND_DISCORD_APPROVAL_STATE:-data/archive/approvals/discord_publish_gate.json}"
export BIZZAL_PUBLISH_REGISTRY="${BIZZAL_DND_PUBLISH_REGISTRY:-data/archive/publish/published_registry.json}"
export BIZZAL_PUBLISH_CMD="${BIZZAL_DND_PUBLISH_CMD:-$REPO_ROOT/bin/upload/upload_youtube.py}"

# Keep feature parity with Shadowdark experiment settings.
export BIZZAL_ENABLE_AI="${BIZZAL_DND_ENABLE_AI:-1}"
export BIZZAL_ENABLE_AI_SCRIPT="${BIZZAL_DND_ENABLE_AI_SCRIPT:-1}"
export BIZZAL_ENABLE_TTS="${BIZZAL_DND_ENABLE_TTS:-1}"
export BIZZAL_ENABLE_BG_IMAGE="${BIZZAL_DND_ENABLE_BG_IMAGE:-1}"
export BIZZAL_ENABLE_BG_MUSIC="${BIZZAL_DND_ENABLE_BG_MUSIC:-1}"
export BIZZAL_ENABLE_PDF_FLAVOR="${BIZZAL_DND_ENABLE_PDF_FLAVOR:-1}"
export BIZZAL_TTS_VOICE_VARIETY_LOOKBACK_DAYS="${BIZZAL_DND_TTS_VOICE_VARIETY_LOOKBACK_DAYS:-7}"

mkdir -p \
  "$REPO_ROOT/$BIZZAL_ATOM_INCOMING_DIR" \
  "$REPO_ROOT/$BIZZAL_ATOM_VALIDATED_DIR" \
  "$REPO_ROOT/$BIZZAL_ATOM_FAILED_DIR" \
  "$REPO_ROOT/$BIZZAL_RENDERS_BY_DAY_DIR" \
  "$REPO_ROOT/$BIZZAL_RENDERS_LATEST_DIR" \
  "$REPO_ROOT/$BIZZAL_RENDERS_TMP_DIR" \
  "$REPO_ROOT/data/archive/approvals" \
  "$REPO_ROOT/data/archive/publish"
