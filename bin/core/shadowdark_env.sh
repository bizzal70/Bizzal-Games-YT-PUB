#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

export BIZZAL_CHAIN_LABEL="shadowdark"
export BIZZAL_CHAIN_TAG="Shadowdark"
export BIZZAL_REFERENCE_SOURCES_PATH="${BIZZAL_SD_REFERENCE_SOURCES_PATH:-config/reference_sources_shadowdark.yaml}"
export BIZZAL_TOPIC_SPINE_PATH="${BIZZAL_SD_TOPIC_SPINE_PATH:-config/topic_spine_shadowdark.yaml}"
export BIZZAL_STYLE_RULES_PATH="${BIZZAL_SD_STYLE_RULES_PATH:-config/style_rules_shadowdark.yaml}"
export BIZZAL_STYLE_HISTORY_PATH="${BIZZAL_SD_STYLE_HISTORY_PATH:-runtime/state/style_history_shadowdark.json}"

export BIZZAL_ACTIVE_SRD_PATH="${BIZZAL_SD_ACTIVE_SRD_PATH:-reference/shadowdark/active}"
export BIZZAL_SRD_PDF_PATH="${BIZZAL_SD_SRD_PDF_PATH:-reference/shadowdark/source_pdfs/Shadowdark_RPG_-_V4-8.pdf}"

export BIZZAL_ATOM_INCOMING_DIR="${BIZZAL_SD_ATOM_INCOMING_DIR:-data/atoms_shadowdark/incoming}"
export BIZZAL_ATOM_VALIDATED_DIR="${BIZZAL_SD_ATOM_VALIDATED_DIR:-data/atoms_shadowdark/validated}"
export BIZZAL_ATOM_FAILED_DIR="${BIZZAL_SD_ATOM_FAILED_DIR:-data/atoms_shadowdark/failed}"

export BIZZAL_RENDERS_BY_DAY_DIR="${BIZZAL_SD_RENDERS_BY_DAY_DIR:-data/renders_shadowdark/by_day}"
export BIZZAL_RENDERS_LATEST_DIR="${BIZZAL_SD_RENDERS_LATEST_DIR:-data/renders_shadowdark/latest}"
export BIZZAL_RENDERS_TMP_DIR="${BIZZAL_SD_RENDERS_TMP_DIR:-data/renders_shadowdark/tmp}"
export BIZZAL_LATEST_VIDEO_PATH="${BIZZAL_SD_LATEST_VIDEO_PATH:-data/renders_shadowdark/latest/latest.mp4}"

export BIZZAL_DISCORD_APPROVAL_STATE="${BIZZAL_SD_DISCORD_APPROVAL_STATE:-data/archive/approvals/discord_publish_gate_shadowdark.json}"
export BIZZAL_PUBLISH_REGISTRY="${BIZZAL_SD_PUBLISH_REGISTRY:-data/archive/publish/published_registry_shadowdark.json}"
export BIZZAL_PUBLISH_CMD="${BIZZAL_SD_PUBLISH_CMD:-$REPO_ROOT/bin/upload/upload_youtube.py}"

mkdir -p \
  "$REPO_ROOT/$BIZZAL_ATOM_INCOMING_DIR" \
  "$REPO_ROOT/$BIZZAL_ATOM_VALIDATED_DIR" \
  "$REPO_ROOT/$BIZZAL_ATOM_FAILED_DIR" \
  "$REPO_ROOT/$BIZZAL_RENDERS_BY_DAY_DIR" \
  "$REPO_ROOT/$BIZZAL_RENDERS_LATEST_DIR" \
  "$REPO_ROOT/$BIZZAL_RENDERS_TMP_DIR" \
  "$REPO_ROOT/logs/shadowdark" \
  "$REPO_ROOT/data/archive/approvals" \
  "$REPO_ROOT/data/archive/publish"
