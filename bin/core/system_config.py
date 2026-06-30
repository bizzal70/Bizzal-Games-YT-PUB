#!/usr/bin/env python3
"""
DB-backed replacement for config/topic_spine*.yaml, config/style_rules*.yaml,
and config/reference_sources*.yaml.

Each load_* function returns the same dict shape that yaml.safe_load() of the
corresponding legacy file produced, so callers (make_atom.py, pick_style.py,
write_script_from_fact.py, reference_paths.py, etc.) don't need to change
their lookup logic -- only the load step changes.

Connection string comes from BIZZAL_DB_URL (a standard postgres:// URI).
"""
import os
from functools import lru_cache

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None


def _connect():
    if psycopg is None:
        raise RuntimeError(
            "psycopg is not installed. Run: python3 -m pip install -r requirements.txt"
        )
    db_url = os.environ.get("BIZZAL_DB_URL")
    if not db_url:
        raise RuntimeError("BIZZAL_DB_URL is not set. See .env.example.")
    return psycopg.connect(db_url)


@lru_cache(maxsize=8)
def _system_row(system_id: str) -> dict:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, display_name, chain_tag, path_suffix, is_active,
                       ruleset, target_seconds, reading_level, no_homebrew_mechanics,
                       default_length, spice_rate, persona_default,
                       voiceover_default_voice_pack_id, voiceover_default_tts_voice_id,
                       active_srd_path, srd_pdf_path, reference_sources,
                       bg_image_prompt_prefix, bg_image_prompt_suffix,
                       music_prompt_prefix, music_prompt_suffix,
                       enable_ai, enable_ai_script, enable_tts,
                       enable_bg_image, enable_bg_music, enable_pdf_flavor,
                       tts_voice_variety_lookback_days
                FROM rpg_systems WHERE id = %s
                """,
                (system_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(f"Unknown rpg_systems.id: {system_id!r}")
            cols = [d.name for d in cur.description]
            return dict(zip(cols, row))


def list_active_system_ids() -> list[str]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM rpg_systems WHERE is_active ORDER BY id")
            return [r[0] for r in cur.fetchall()]


def get_system(system_id: str) -> dict:
    """Raw rpg_systems row as a dict -- used by system_env.sh's Python helper
    and anywhere that needs chain_tag/path_suffix/feature flags directly."""
    return _system_row(system_id)


def load_topic_spine(system_id: str) -> dict:
    """Returns {weekly_spine, defaults, category_weights} -- same shape as
    the old topic_spine.yaml."""
    sysrow = _system_row(system_id)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT day_of_week, category FROM system_weekly_spine WHERE system_id = %s",
                (system_id,),
            )
            weekly_spine = dict(cur.fetchall())

            cur.execute(
                "SELECT category, angle, weight FROM system_category_angle_weights WHERE system_id = %s",
                (system_id,),
            )
            category_weights: dict = {}
            for category, angle, weight in cur.fetchall():
                category_weights.setdefault(category, {"angles": {}})["angles"][angle] = weight

    return {
        "weekly_spine": weekly_spine,
        "defaults": {
            "ruleset": sysrow["ruleset"],
            "target_seconds": sysrow["target_seconds"],
            "reading_level": sysrow["reading_level"],
            "no_homebrew_mechanics": sysrow["no_homebrew_mechanics"],
        },
        "category_weights": category_weights,
    }


def load_style_rules(system_id: str) -> dict:
    """Returns {defaults, persona_by_category, tones_by_category,
    voiceover_by_tone, voiceover_by_voice, persona_profiles, voices,
    category_rules} -- same shape as the old style_rules.yaml."""
    sysrow = _system_row(system_id)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT category, persona, tones, voices, angles FROM system_categories WHERE system_id = %s",
                (system_id,),
            )
            persona_by_category = {}
            tones_by_category = {}
            category_rules = {}
            for category, persona, tones, voices, angles in cur.fetchall():
                if persona:
                    persona_by_category[category] = persona
                if tones:
                    tones_by_category[category] = list(tones)
                category_rules[category] = {"angles": list(angles), "voices": list(voices)}

            cur.execute(
                "SELECT tone, voice_pack_id, tts_voice_ids FROM system_tones WHERE system_id = %s",
                (system_id,),
            )
            voiceover_by_tone = {
                tone: {"voice_pack_id": vpid, "tts_voice_ids": list(ids or [])}
                for tone, vpid, ids in cur.fetchall()
            }

            cur.execute(
                "SELECT voice_name, tts_voice_ids, hooks, ctas FROM system_voices WHERE system_id = %s",
                (system_id,),
            )
            voices_block: dict = {}
            voiceover_by_voice: dict = {}
            for voice_name, tts_ids, hooks, ctas in cur.fetchall():
                voices_block[voice_name] = {"hooks": list(hooks), "ctas": list(ctas)}
                if tts_ids:
                    voiceover_by_voice[voice_name] = {"tts_voice_ids": list(tts_ids)}

            cur.execute(
                "SELECT voice_name, category, hooks, ctas FROM system_voice_category_lines WHERE system_id = %s",
                (system_id,),
            )
            for voice_name, category, hooks, ctas in cur.fetchall():
                if voice_name not in voices_block:
                    continue
                if hooks:
                    voices_block[voice_name][f"hooks_{category}"] = list(hooks)
                if ctas:
                    voices_block[voice_name][f"ctas_{category}"] = list(ctas)

            cur.execute(
                "SELECT persona, one_liner FROM system_personas WHERE system_id = %s",
                (system_id,),
            )
            persona_profiles = {p: {"one_liner": ol} for p, ol in cur.fetchall()}

    return {
        "defaults": {
            "length": sysrow["default_length"],
            "spice_rate": sysrow["spice_rate"],
            "tones": _default_tone_pool(voiceover_by_tone),
            "persona_default": sysrow["persona_default"],
            "voiceover_default": {
                "voice_pack_id": sysrow["voiceover_default_voice_pack_id"],
                "tts_voice_id": sysrow["voiceover_default_tts_voice_id"],
            },
        },
        "persona_by_category": persona_by_category,
        "tones_by_category": tones_by_category,
        "voiceover_by_tone": voiceover_by_tone,
        "voiceover_by_voice": voiceover_by_voice,
        "persona_profiles": persona_profiles,
        "voices": voices_block,
        "category_rules": category_rules,
    }


def _default_tone_pool(voiceover_by_tone: dict) -> list:
    return list(voiceover_by_tone.keys())


def load_reference_sources(system_id: str) -> dict:
    """Returns {active_srd_path, srd_pdf_path, sources} -- same shape as the
    old reference_sources.yaml."""
    sysrow = _system_row(system_id)
    return {
        "active_srd_path": sysrow["active_srd_path"],
        "srd_pdf_path": sysrow["srd_pdf_path"],
        "sources": sysrow["reference_sources"] or {},
    }
