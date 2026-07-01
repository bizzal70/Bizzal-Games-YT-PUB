#!/usr/bin/env python3
"""
One-off migration: backfills rpg_systems + child tables in Postgres from the
current config/topic_spine*.yaml, config/style_rules*.yaml, and
config/reference_sources*.yaml content (dnd5e and shadowdark).

Run once against the real DB after bin/core/db_schema.sql has been applied:
    BIZZAL_DB_URL=postgresql://... python3 bin/core/migrate_config_to_db.py

Then verify with bin/core/verify_config_migration.py before deleting the
YAML files / wrapper scripts.
"""
import os
import sys

try:
    import psycopg
    from psycopg.types.json import Json
except ImportError:
    print("ERROR: psycopg not installed. pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Source data, transcribed from config/*.yaml as of the Phase 0/1 scrub.
# ---------------------------------------------------------------------------

SYSTEMS = {
    "dnd5e": dict(
        display_name="D&D 5e",
        chain_tag="D&D",
        path_suffix="",
        ruleset="wotc_srd_2024",
        target_seconds=55,
        reading_level="general",
        no_homebrew_mechanics=True,
        default_length="shorts",
        spice_rate=0.35,
        persona_default="table_coach",
        voiceover_default_voice_pack_id="voice-friendly-vet",
        voiceover_default_tts_voice_id="alloy",
        active_srd_path="reference/systems/dnd5e/active",
        srd_pdf_path="reference/systems/dnd5e/source_pdfs/SRD_CC_v5.2.1.pdf",
        bg_image_prompt_prefix="",
        bg_image_prompt_suffix="",
        music_prompt_prefix="",
        music_prompt_suffix="",
        enable_ai=True,
        enable_ai_script=True,
        enable_tts=True,
        enable_bg_image=True,
        enable_bg_music=True,
        enable_pdf_flavor=True,
        tts_voice_variety_lookback_days=7,
        reference_sources={
            "creatures": {"file": "Creature.json", "joins": {"actions": "CreatureAction.json", "attacks": "CreatureActionAttack.json", "traits": "CreatureTrait.json"}},
            "spells": {"file": "Spell.json", "joins": {"casting_options": "SpellCastingOption.json"}},
            "items": {"file": "Item.json", "joins": {"item_category": "ItemCategory.json"}, "also": {"armor": "Armor.json", "weapons": "Weapon.json", "weapon_properties": "WeaponProperty.json", "weapon_property_assignments": "WeaponPropertyAssignment.json"}},
            "classes": {"file": "CharacterClass.json", "joins": {"features": "ClassFeature.json", "feature_items": "ClassFeatureItem.json"}},
            "rules": {"file": "Rule.json", "joins": {"rulesets": "RuleSet.json"}},
            "species": {"file": "Species.json", "joins": {"traits": "SpeciesTrait.json"}},
            "flavor": {"alignment": "AlignmentDescription.json", "ability": "AbilityDescription.json", "condition": "ConditionDescription.json", "damage_type": "DamageTypeDescription.json", "creature_type": "CreatureTypeDescription.json", "environment": None},
        },
    ),
    "shadowdark": dict(
        display_name="Shadowdark",
        chain_tag="Shadowdark",
        path_suffix="_shadowdark",
        ruleset="shadowdark_v4_8",
        target_seconds=55,
        reading_level="general",
        no_homebrew_mechanics=True,
        default_length="shorts",
        spice_rate=0.4,
        persona_default="torchbearer_referee",
        voiceover_default_voice_pack_id="voice-shadowdark-ref",
        voiceover_default_tts_voice_id="onyx",
        active_srd_path="reference/systems/shadowdark/active",
        srd_pdf_path="reference/systems/shadowdark/source_pdfs/Shadowdark_RPG_-_V4-8.pdf",
        bg_image_prompt_prefix="shadowdark aesthetic, dangerous dungeon crawl, torchlight and deep shadow, gritty old-school fantasy",
        bg_image_prompt_suffix="",
        music_prompt_prefix="shadowdark tone, tense dungeon exploration, low-magic peril, restrained ominous ambience",
        music_prompt_suffix="",
        enable_ai=True,
        enable_ai_script=True,
        enable_tts=True,
        enable_bg_image=True,
        enable_bg_music=True,
        enable_pdf_flavor=True,
        tts_voice_variety_lookback_days=7,
        reference_sources={
            "creatures": {"file": "Creature.json", "joins": {"actions": "CreatureAction.json", "attacks": "CreatureActionAttack.json", "traits": "CreatureTrait.json"}},
            "spells": {"file": "Spell.json", "joins": {"casting_options": "SpellCastingOption.json"}},
            "items": {"file": "Item.json"},
            "classes": {"file": "CharacterClass.json"},
            "rules": {"file": "Rule.json"},
        },
    ),
}

WEEKLY_SPINE = {
    "dnd5e": {"mon": "monster_tactic", "tue": "spell_use_case", "wed": "rules_ruling", "thu": "item_spotlight", "fri": "encounter_seed", "sat": "rules_myth", "sun": "class_spotlight"},
    "shadowdark": {"mon": "monster_tactic", "tue": "rules_ruling", "wed": "item_spotlight", "thu": "encounter_seed", "fri": "rules_myth", "sat": "spell_use_case", "sun": "class_spotlight"},
}

CATEGORY_ANGLE_WEIGHTS = {
    "dnd5e": {
        "monster_tactic": {"how_it_wins": 3, "how_to_counter": 3, "terrain_synergy": 2, "party_level_scaling": 2, "roleplay_hook": 1},
        "spell_use_case": {"best_moment": 3, "combo_pairing": 2, "common_mistake": 2, "upcast_tip": 2, "dm_counterplay": 1},
        "rules_ruling": {"common_table_mistake": 3, "fast_ruling": 3, "edge_case": 2, "dm_fairness_tip": 2, "player_tip": 1},
        "item_spotlight": {"best_user": 3, "clever_use": 3, "drawback_watchout": 2, "dm_counterplay": 2, "story_hook": 1},
        "encounter_seed": {"three_beats": 3, "twist": 3, "terrain_feature": 2, "time_pressure": 2, "moral_choice": 1},
        "rules_myth": {"myth_vs_rule": 4, "why_people_get_it_wrong": 2, "quick_example": 2, "dm_callout": 1},
        "character_micro_tip": {"level_1_choice": 3, "party_role": 3, "survivability": 2, "exploration_edge": 2, "table_etiquette": 1},
        "class_spotlight": {"early_power_spike": 3, "subclass_identity": 3, "resource_breakpoint": 2, "party_role_pivot": 2, "progression_trap": 1},
    },
    "shadowdark": {
        "monster_tactic": {"how_it_wins": 3, "how_to_counter": 3, "common_mistake": 2, "terrain_synergy": 2},
        "spell_use_case": {"best_moment": 3, "common_mistake": 3, "dm_counterplay": 2, "combo_pairing": 2},
        "rules_ruling": {"fast_ruling": 3, "common_table_mistake": 3, "edge_case": 2, "player_tip": 2},
        "item_spotlight": {"clever_use": 3, "best_user": 3, "drawback_watchout": 2, "story_hook": 2},
        "encounter_seed": {"three_beats": 3, "twist": 3, "time_pressure": 2, "moral_choice": 2},
        "rules_myth": {"myth_vs_rule": 4, "quick_example": 3, "why_people_get_it_wrong": 2},
        "class_spotlight": {"early_power_spike": 3, "party_role_pivot": 3, "progression_trap": 2, "resource_breakpoint": 2},
    },
}

PERSONA_BY_CATEGORY = {
    "dnd5e": {"monster_tactic": "tactical_analyst", "spell_use_case": "clever_table_vet", "item_spotlight": "clever_table_vet", "encounter_seed": "dm_story_coach", "rules_ruling": "rules_referee", "rules_myth": "rules_referee", "character_micro_tip": "class_mentor", "gm_tip": "rules_referee", "roleplaying_tip": "class_mentor", "character_class_spotlight": "class_mentor", "class_spotlight": "class_mentor", "dungeoneering_encounter": "dm_story_coach", "overworld_encounter": "dm_story_coach"},
    "shadowdark": {"monster_tactic": "tactical_analyst", "spell_use_case": "arcane_survival_coach", "item_spotlight": "dungeon_gear_mentor", "encounter_seed": "dm_story_coach", "rules_ruling": "rules_referee", "rules_myth": "rules_referee", "class_spotlight": "class_mentor", "character_micro_tip": "class_mentor"},
}

TONES_BY_CATEGORY = {
    "dnd5e": {"monster_tactic": ["gritty", "neutral"], "spell_use_case": ["neutral", "heroic"], "item_spotlight": ["neutral", "heroic"], "encounter_seed": ["gritty", "heroic"], "rules_ruling": ["neutral"], "rules_myth": ["neutral"], "character_micro_tip": ["heroic", "neutral"], "class_spotlight": ["heroic", "neutral"]},
    "shadowdark": {"monster_tactic": ["gritty", "ominous"], "spell_use_case": ["gritty", "neutral"], "item_spotlight": ["gritty", "neutral"], "encounter_seed": ["ominous", "gritty"], "rules_ruling": ["neutral", "gritty"], "rules_myth": ["neutral", "gritty"], "class_spotlight": ["gritty", "neutral"], "character_micro_tip": ["gritty", "neutral"]},
}

CATEGORY_RULES = {
    "dnd5e": {
        "monster_tactic": {"angles": ["how_it_wins", "common_mistake", "counterplay"], "voices": ["gritty_dm", "rules_lawyer", "friendly_vet"]},
        "spell_use_case": {"angles": ["best_moment", "common_misplay", "dm_twist", "combo_pairing", "upcast_tip", "dm_counterplay"], "voices": ["friendly_vet", "rules_lawyer", "gritty_dm"]},
        "item_spotlight": {"angles": ["best_user", "clever_use", "drawback_watchout", "dm_counterplay", "story_hook"], "voices": ["friendly_vet", "rules_lawyer", "gritty_dm"]},
        "encounter_seed": {"angles": ["three_beats", "twist", "terrain_feature", "time_pressure", "moral_choice"], "voices": ["gritty_dm", "friendly_vet", "rules_lawyer"]},
        "rules_ruling": {"angles": ["common_table_mistake", "fast_ruling", "edge_case", "dm_fairness_tip", "player_tip"], "voices": ["rules_lawyer", "friendly_vet", "gritty_dm"]},
        "rules_myth": {"angles": ["myth_vs_rule", "why_people_get_it_wrong", "quick_example", "dm_callout"], "voices": ["rules_lawyer", "friendly_vet", "gritty_dm"]},
        "character_micro_tip": {"angles": ["level_1_choice", "party_role", "survivability", "exploration_edge", "table_etiquette"], "voices": ["friendly_vet", "gritty_dm", "rules_lawyer"]},
        "gm_tip": {"angles": ["common_table_mistake", "fast_ruling", "edge_case", "dm_fairness_tip", "player_tip"], "voices": ["rules_lawyer", "friendly_vet", "gritty_dm"]},
        "roleplaying_tip": {"angles": ["level_1_choice", "party_role", "survivability", "exploration_edge", "table_etiquette"], "voices": ["friendly_vet", "gritty_dm", "rules_lawyer"]},
        "character_class_spotlight": {"angles": ["level_1_choice", "party_role", "survivability", "exploration_edge", "table_etiquette"], "voices": ["friendly_vet", "gritty_dm", "rules_lawyer"]},
        "class_spotlight": {"angles": ["early_power_spike", "subclass_identity", "resource_breakpoint", "party_role_pivot", "progression_trap"], "voices": ["friendly_vet", "gritty_dm", "rules_lawyer"]},
        "dungeoneering_encounter": {"angles": ["three_beats", "twist", "terrain_feature", "time_pressure", "moral_choice"], "voices": ["gritty_dm", "friendly_vet", "rules_lawyer"]},
        "overworld_encounter": {"angles": ["three_beats", "twist", "terrain_feature", "time_pressure", "moral_choice"], "voices": ["gritty_dm", "friendly_vet", "rules_lawyer"]},
    },
    "shadowdark": {
        "monster_tactic": {"angles": ["how_it_wins", "common_mistake", "counterplay"], "voices": ["grim_warden", "strict_referee", "torchbearer_ref"]},
        "spell_use_case": {"angles": ["best_moment", "common_misplay", "dm_twist"], "voices": ["torchbearer_ref", "strict_referee", "grim_warden"]},
        "item_spotlight": {"angles": ["clever_use", "best_user", "drawback_watchout"], "voices": ["torchbearer_ref", "grim_warden", "strict_referee"]},
        "encounter_seed": {"angles": ["three_beats", "twist", "time_pressure", "moral_choice"], "voices": ["grim_warden", "torchbearer_ref", "strict_referee"]},
        "rules_ruling": {"angles": ["fast_ruling", "common_table_mistake", "edge_case"], "voices": ["strict_referee", "torchbearer_ref", "grim_warden"]},
        "rules_myth": {"angles": ["myth_vs_rule", "quick_example", "dm_callout"], "voices": ["strict_referee", "torchbearer_ref", "grim_warden"]},
        "class_spotlight": {"angles": ["early_power_spike", "party_role_pivot", "progression_trap"], "voices": ["torchbearer_ref", "grim_warden", "strict_referee"]},
        "character_micro_tip": {"angles": ["level_1_choice", "party_role", "survivability"], "voices": ["torchbearer_ref", "grim_warden", "strict_referee"]},
    },
}

VOICEOVER_BY_TONE = {
    "dnd5e": {
        "neutral": {"voice_pack_id": "voice-friendly-vet", "tts_voice_ids": ["alloy", "ash"]},
        "gritty": {"voice_pack_id": "voice-gritty-dm", "tts_voice_ids": ["onyx", "echo"]},
        "heroic": {"voice_pack_id": "voice-class-mentor", "tts_voice_ids": ["nova", "fable"]},
    },
    "shadowdark": {
        "neutral": {"voice_pack_id": "voice-shadowdark-ref", "tts_voice_ids": ["ash", "alloy"]},
        "gritty": {"voice_pack_id": "voice-shadowdark-grit", "tts_voice_ids": ["onyx", "echo"]},
        "ominous": {"voice_pack_id": "voice-shadowdark-ominous", "tts_voice_ids": ["onyx", "fable"]},
    },
}

VOICEOVER_BY_VOICE = {
    "dnd5e": {
        "friendly_vet": ["alloy", "ash"],
        "gritty_dm": ["onyx", "echo"],
        "rules_lawyer": ["sage", "ash"],
    },
    "shadowdark": {},  # not present in the Shadowdark YAML
}

PERSONA_PROFILES = {
    "dnd5e": {
        "dm_story_coach": "Clear, dramatic, and practical DM guidance with concrete stakes.",
        "rules_referee": "Crisp, fair, and consistent rules adjudication voice.",
        "class_mentor": "Encouraging, role-aware class coaching focused on better decisions.",
        "tactical_analyst": "Serious threat-first tactical framing with minimal fluff.",
        "clever_table_vet": "Practical table wisdom with a bit of personality and momentum.",
        "table_coach": "Friendly veteran table coach balancing clarity and fun.",
    },
    "shadowdark": {
        "torchbearer_referee": "Practical, high-stakes guidance for lethal dungeon play.",
        "tactical_analyst": "Threat-first tactics with strict economy of action.",
        "arcane_survival_coach": "Spell use focused on survival, tempo, and risk control.",
        "dungeon_gear_mentor": "Resource-first gear coaching for dangerous exploration.",
        "dm_story_coach": "Tight encounter framing with pressure and consequence.",
        "rules_referee": "Crisp rulings that keep momentum and fairness.",
        "class_mentor": "Role-focused class guidance with concrete play impact.",
    },
}

VOICES = {
    "dnd5e": {
        "friendly_vet": {
            "hooks": ["Old-school kit check: {name}.", "Dungeon kit spotlight: {name}."],
            "ctas": ["DMs: drop one in the dungeon and watch the party start thinking like engineers.", "Players: buy this before your next shiny weapon."],
            "category_lines": {
                "monster_tactic": {"hooks": ["Monster check: {name}.", "Table troublemaker: {name}."], "ctas": ["DMs: run it like it wants to win, not like it wants to die politely.", "Players: solve the monster, don’t just swing at it."]},
                "spell_use_case": {"hooks": ["Spell play: {name}.", "Pocket magic: {name}."], "ctas": ["DMs: let clever casting change the scene.", "Players: don’t cast it—*aim* it."]},
            },
        },
        "gritty_dm": {
            "hooks": ["In the dark, rope beats steel: {name}.", "This is how you move the world: {name}."],
            "ctas": ["DMs: make the environment heavy. Let tools matter.", "Players: win fights by winning terrain first."],
            "category_lines": {
                "monster_tactic": {"hooks": ["In the dark, {name} is a problem.", "Tonight’s lesson: {name}."], "ctas": ["DMs: hit hard, then disengage—predators don’t trade blows.", "Players: control space or bleed for it."]},
                "spell_use_case": {"hooks": ["Magic with teeth: {name}.", "When it matters: {name}."], "ctas": ["DMs: make magic costly, not pointless.", "Players: spend the slot when it swings the fight."]},
            },
        },
        "rules_lawyer": {
            "hooks": ["Mechanics moment: {name}.", "Rules-forward pick: {name}."],
            "ctas": ["If you want ‘smart play’, reward prep like this.", "Track time, anchors, and positioning—this is where it earns its keep."],
            "category_lines": {
                "monster_tactic": {"hooks": ["Statblock truth: {name}.", "Tactics note: {name}."], "ctas": ["DMs: reward good positioning; punish sloppy clustering.", "Players: deny advantage, deny actions, deny turns."]},
                "spell_use_case": {"hooks": ["Spell timing note: {name}.", "Rules nugget: {name}."], "ctas": ["DMs: enforce components and concentration—spells get sharper.", "Players: read the target line twice, then cast."]},
            },
        },
    },
    "shadowdark": {
        "torchbearer_ref": {"hooks": ["Torchlight briefing: {name}.", "Dungeon brief: {name}."], "ctas": ["DMs: put pressure on time, light, and noise.", "Players: solve for survival before style points."], "category_lines": {}},
        "grim_warden": {"hooks": ["In the dark, {name} matters.", "Hard lesson: {name}."], "ctas": ["DMs: reward caution and punish noise.", "Players: win with prep, not bravado."], "category_lines": {}},
        "strict_referee": {"hooks": ["Ruling check: {name}.", "Table call: {name}."], "ctas": ["Keep rulings fast, clear, and consistent.", "Call intent first, then roll."], "category_lines": {}},
    },
}


def main():
    db_url = os.environ.get("BIZZAL_DB_URL")
    if not db_url:
        print("ERROR: set BIZZAL_DB_URL to your Supabase Postgres connection string.", file=sys.stderr)
        sys.exit(1)

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for system_id, fields in SYSTEMS.items():
                ref_sources = fields.pop("reference_sources")
                cur.execute(
                    """
                    INSERT INTO rpg_systems (
                        id, display_name, chain_tag, path_suffix, ruleset, target_seconds,
                        reading_level, no_homebrew_mechanics, default_length, spice_rate,
                        persona_default, voiceover_default_voice_pack_id, voiceover_default_tts_voice_id,
                        active_srd_path, srd_pdf_path, reference_sources,
                        bg_image_prompt_prefix, bg_image_prompt_suffix, music_prompt_prefix, music_prompt_suffix,
                        enable_ai, enable_ai_script, enable_tts, enable_bg_image, enable_bg_music,
                        enable_pdf_flavor, tts_voice_variety_lookback_days
                    ) VALUES (
                        %(id)s, %(display_name)s, %(chain_tag)s, %(path_suffix)s, %(ruleset)s, %(target_seconds)s,
                        %(reading_level)s, %(no_homebrew_mechanics)s, %(default_length)s, %(spice_rate)s,
                        %(persona_default)s, %(voiceover_default_voice_pack_id)s, %(voiceover_default_tts_voice_id)s,
                        %(active_srd_path)s, %(srd_pdf_path)s, %(reference_sources)s,
                        %(bg_image_prompt_prefix)s, %(bg_image_prompt_suffix)s, %(music_prompt_prefix)s, %(music_prompt_suffix)s,
                        %(enable_ai)s, %(enable_ai_script)s, %(enable_tts)s, %(enable_bg_image)s, %(enable_bg_music)s,
                        %(enable_pdf_flavor)s, %(tts_voice_variety_lookback_days)s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        display_name = EXCLUDED.display_name, chain_tag = EXCLUDED.chain_tag,
                        path_suffix = EXCLUDED.path_suffix, ruleset = EXCLUDED.ruleset,
                        target_seconds = EXCLUDED.target_seconds, reading_level = EXCLUDED.reading_level,
                        no_homebrew_mechanics = EXCLUDED.no_homebrew_mechanics, default_length = EXCLUDED.default_length,
                        spice_rate = EXCLUDED.spice_rate, persona_default = EXCLUDED.persona_default,
                        voiceover_default_voice_pack_id = EXCLUDED.voiceover_default_voice_pack_id,
                        voiceover_default_tts_voice_id = EXCLUDED.voiceover_default_tts_voice_id,
                        active_srd_path = EXCLUDED.active_srd_path, srd_pdf_path = EXCLUDED.srd_pdf_path,
                        reference_sources = EXCLUDED.reference_sources,
                        bg_image_prompt_prefix = EXCLUDED.bg_image_prompt_prefix,
                        bg_image_prompt_suffix = EXCLUDED.bg_image_prompt_suffix,
                        music_prompt_prefix = EXCLUDED.music_prompt_prefix,
                        music_prompt_suffix = EXCLUDED.music_prompt_suffix,
                        enable_ai = EXCLUDED.enable_ai, enable_ai_script = EXCLUDED.enable_ai_script,
                        enable_tts = EXCLUDED.enable_tts, enable_bg_image = EXCLUDED.enable_bg_image,
                        enable_bg_music = EXCLUDED.enable_bg_music, enable_pdf_flavor = EXCLUDED.enable_pdf_flavor,
                        tts_voice_variety_lookback_days = EXCLUDED.tts_voice_variety_lookback_days,
                        updated_at = now()
                    """,
                    {"id": system_id, "reference_sources": Json(ref_sources), **fields},
                )

                cur.execute("DELETE FROM system_weekly_spine WHERE system_id = %s", (system_id,))
                for day, category in WEEKLY_SPINE[system_id].items():
                    cur.execute(
                        "INSERT INTO system_weekly_spine (system_id, day_of_week, category) VALUES (%s, %s, %s)",
                        (system_id, day, category),
                    )

                cur.execute("DELETE FROM system_category_angle_weights WHERE system_id = %s", (system_id,))
                for category, angles in CATEGORY_ANGLE_WEIGHTS[system_id].items():
                    for angle, weight in angles.items():
                        cur.execute(
                            "INSERT INTO system_category_angle_weights (system_id, category, angle, weight) VALUES (%s, %s, %s, %s)",
                            (system_id, category, angle, weight),
                        )

                cur.execute("DELETE FROM system_categories WHERE system_id = %s", (system_id,))
                categories = set(CATEGORY_RULES[system_id].keys())
                for category in categories:
                    rules = CATEGORY_RULES[system_id][category]
                    cur.execute(
                        """
                        INSERT INTO system_categories (system_id, category, persona, tones, voices, angles)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            system_id,
                            category,
                            PERSONA_BY_CATEGORY[system_id].get(category),
                            TONES_BY_CATEGORY[system_id].get(category),
                            rules["voices"],
                            rules["angles"],
                        ),
                    )

                cur.execute("DELETE FROM system_tones WHERE system_id = %s", (system_id,))
                for tone, vo in VOICEOVER_BY_TONE[system_id].items():
                    cur.execute(
                        "INSERT INTO system_tones (system_id, tone, voice_pack_id, tts_voice_ids) VALUES (%s, %s, %s, %s)",
                        (system_id, tone, vo["voice_pack_id"], vo["tts_voice_ids"]),
                    )

                cur.execute("DELETE FROM system_voices WHERE system_id = %s", (system_id,))
                cur.execute("DELETE FROM system_voice_category_lines WHERE system_id = %s", (system_id,))
                for voice_name, vdata in VOICES[system_id].items():
                    tts_ids = VOICEOVER_BY_VOICE[system_id].get(voice_name)
                    cur.execute(
                        "INSERT INTO system_voices (system_id, voice_name, tts_voice_ids, hooks, ctas) VALUES (%s, %s, %s, %s, %s)",
                        (system_id, voice_name, tts_ids, vdata["hooks"], vdata["ctas"]),
                    )
                    for category, lines in vdata.get("category_lines", {}).items():
                        cur.execute(
                            "INSERT INTO system_voice_category_lines (system_id, voice_name, category, hooks, ctas) VALUES (%s, %s, %s, %s, %s)",
                            (system_id, voice_name, category, lines.get("hooks"), lines.get("ctas")),
                        )

                cur.execute("DELETE FROM system_personas WHERE system_id = %s", (system_id,))
                for persona, one_liner in PERSONA_PROFILES[system_id].items():
                    cur.execute(
                        "INSERT INTO system_personas (system_id, persona, one_liner) VALUES (%s, %s, %s)",
                        (system_id, persona, one_liner),
                    )

        conn.commit()
    print("Migration complete: dnd5e, shadowdark.")


if __name__ == "__main__":
    main()
