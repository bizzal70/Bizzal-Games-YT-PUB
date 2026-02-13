#!/usr/bin/env python3
import os

try:
    import yaml
except ImportError:
    yaml = None


def load_reference_config(cfg_path: str) -> dict:
    if not os.path.exists(cfg_path) or yaml is None:
        return {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _normalize_path(repo_root: str, path_value: str) -> str:
    p = (path_value or "").strip()
    if not p:
        return ""
    if not os.path.isabs(p):
        p = os.path.join(repo_root, p)
    return os.path.realpath(p)


def resolve_active_srd_path(repo_root: str, cfg_path: str) -> tuple[str, dict]:
    cfg = load_reference_config(cfg_path)

    env_override = (
        os.getenv("BIZZAL_ACTIVE_SRD_PATH")
        or os.getenv("BG_ACTIVE_SRD_PATH")
        or ""
    )

    cfg_path_value = ""
    if isinstance(cfg, dict):
        cfg_path_value = cfg.get("active_srd_path") or ""

    default_active_path = os.path.join(repo_root, "reference", "active")
    legacy_default_path = os.path.join(repo_root, "reference", "srd5.1")

    for candidate in (env_override, cfg_path_value, default_active_path, legacy_default_path):
        resolved = _normalize_path(repo_root, candidate)
        if resolved and os.path.isdir(resolved):
            return resolved, cfg

    # Return normalized preferred path even if missing so caller can show useful errors.
    preferred = _normalize_path(repo_root, env_override or cfg_path_value or default_active_path)
    return preferred, cfg


def resolve_srd_pdf_path(repo_root: str, cfg_path: str) -> tuple[str, dict]:
    cfg = load_reference_config(cfg_path)

    env_override = (
        os.getenv("BIZZAL_SRD_PDF_PATH")
        or os.getenv("BG_SRD_PDF_PATH")
        or ""
    )

    cfg_value = ""
    if isinstance(cfg, dict):
        cfg_value = cfg.get("srd_pdf_path") or ""

    default_pdf_path = os.path.join(repo_root, "reference", "srd", "SRD_CC_v5.2.1.pdf")

    for candidate in (env_override, cfg_value, default_pdf_path):
        resolved = _normalize_path(repo_root, candidate)
        if resolved and os.path.isfile(resolved):
            return resolved, cfg

    preferred = _normalize_path(repo_root, env_override or cfg_value or default_pdf_path)
    return preferred, cfg
