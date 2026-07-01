#!/usr/bin/env python3
"""
One-time migration: update tone/persona data in Supabase to the 'wry_vet' voice.

What changes:
- rpg_systems: persona_default -> 'wry_vet', spice_rate -> 0.6
- system_tones: rename 'neutral' -> 'dry', add 'wry' and 'sardonic' tones
- system_personas: upsert 'wry_vet' persona for both systems
- system_categories: update default persona to 'wry_vet' where 'table_coach'

Run once:
  python3 bin/core/migrate_tone_to_wry_vet.py
"""
import os, sys

sys.path.insert(0, os.path.dirname(__file__))

try:
    import psycopg
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg[binary]", "-q"])
    import psycopg

DB_URL = os.environ.get("BIZZAL_DB_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    print("ERROR: set BIZZAL_DB_URL before running this script.", file=sys.stderr)
    sys.exit(1)

WRY_VET_LINER = (
    "Dry, world-weary veteran DM who has run this encounter a hundred times. "
    "Authoritative, specific, slightly sardonic. No hype. No hand-holding. "
    "Calls the table's bad habits what they are. Assumes the reader has been around."
)

SYSTEMS = ["dnd5e", "shadowdark"]

NEW_TONES = [
    # (tone_name, voice_pack_id, tts_voice_ids)
    ("dry",      "voice-wry-vet", ["onyx", "fable"]),
    ("wry",      "voice-wry-vet", ["onyx", "fable"]),
    ("sardonic", "voice-wry-vet", ["onyx"]),
    ("deadpan",  "voice-wry-vet", ["onyx", "fable"]),
    ("punchy",   "voice-wry-vet", ["fable"]),
]

def run():
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            for sys_id in SYSTEMS:
                # 1. Update rpg_systems defaults
                cur.execute("""
                    UPDATE rpg_systems
                    SET persona_default = 'wry_vet',
                        spice_rate      = 0.6
                    WHERE id = %s
                """, (sys_id,))
                print(f"[{sys_id}] rpg_systems updated: persona_default=wry_vet, spice_rate=0.6")

                # 2. Upsert wry_vet persona
                cur.execute("""
                    INSERT INTO system_personas (system_id, persona, one_liner)
                    VALUES (%s, 'wry_vet', %s)
                    ON CONFLICT (system_id, persona) DO UPDATE
                        SET one_liner = EXCLUDED.one_liner
                """, (sys_id, WRY_VET_LINER))
                print(f"[{sys_id}] system_personas upserted: wry_vet")

                # 3. Remove old 'neutral' tone row if present, upsert new tones
                cur.execute("DELETE FROM system_tones WHERE system_id = %s AND tone = 'neutral'", (sys_id,))
                for tone_name, vpid, tts_ids in NEW_TONES:
                    cur.execute("""
                        INSERT INTO system_tones (system_id, tone, voice_pack_id, tts_voice_ids)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (system_id, tone) DO UPDATE
                            SET voice_pack_id = EXCLUDED.voice_pack_id,
                                tts_voice_ids = EXCLUDED.tts_voice_ids
                    """, (sys_id, tone_name, vpid, tts_ids))
                print(f"[{sys_id}] system_tones upserted: {[t[0] for t in NEW_TONES]}")

                # 4. Flip category personas from table_coach -> wry_vet
                cur.execute("""
                    UPDATE system_categories
                    SET persona = 'wry_vet'
                    WHERE system_id = %s AND persona = 'table_coach'
                """, (sys_id,))
                rows = cur.rowcount
                print(f"[{sys_id}] system_categories updated {rows} rows: table_coach -> wry_vet")

                # 5. Replace neutral in tones arrays for each category
                cur.execute("""
                    UPDATE system_categories
                    SET tones = array_replace(tones, 'neutral', 'dry')
                    WHERE system_id = %s AND 'neutral' = ANY(tones)
                """, (sys_id,))
                rows = cur.rowcount
                print(f"[{sys_id}] system_categories tones: replaced 'neutral' with 'dry' in {rows} rows")

        conn.commit()
        print("\nDone. All tone/persona data migrated to wry_vet voice.")

if __name__ == "__main__":
    run()
