#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

export BIZZAL_CHAIN_LABEL="shadowdark"
export BIZZAL_REFERENCE_SOURCES_PATH="${BIZZAL_REFERENCE_SOURCES_PATH:-config/reference_sources_shadowdark.yaml}"
export BIZZAL_TOPIC_SPINE_PATH="${BIZZAL_TOPIC_SPINE_PATH:-config/topic_spine_shadowdark.yaml}"
export BIZZAL_STYLE_RULES_PATH="${BIZZAL_STYLE_RULES_PATH:-config/style_rules_shadowdark.yaml}"
export BIZZAL_STYLE_HISTORY_PATH="${BIZZAL_STYLE_HISTORY_PATH:-runtime/state/style_history_shadowdark.json}"

export BIZZAL_ATOM_INCOMING_DIR="${BIZZAL_ATOM_INCOMING_DIR:-data/atoms_shadowdark/incoming}"
export BIZZAL_ATOM_VALIDATED_DIR="${BIZZAL_ATOM_VALIDATED_DIR:-data/atoms_shadowdark/validated}"
export BIZZAL_ATOM_FAILED_DIR="${BIZZAL_ATOM_FAILED_DIR:-data/atoms_shadowdark/failed}"

export BIZZAL_RENDERS_BY_DAY_DIR="${BIZZAL_RENDERS_BY_DAY_DIR:-data/renders_shadowdark/by_day}"
export BIZZAL_RENDERS_LATEST_DIR="${BIZZAL_RENDERS_LATEST_DIR:-data/renders_shadowdark/latest}"
export BIZZAL_RENDERS_TMP_DIR="${BIZZAL_RENDERS_TMP_DIR:-data/renders_shadowdark/tmp}"
export BIZZAL_LATEST_VIDEO_PATH="${BIZZAL_LATEST_VIDEO_PATH:-data/renders_shadowdark/latest/latest.mp4}"

export BIZZAL_DISCORD_APPROVAL_STATE="${BIZZAL_DISCORD_APPROVAL_STATE:-data/archive/approvals/discord_publish_gate_shadowdark.json}"
export BIZZAL_PUBLISH_REGISTRY="${BIZZAL_PUBLISH_REGISTRY:-data/archive/publish/published_registry_shadowdark.json}"

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
