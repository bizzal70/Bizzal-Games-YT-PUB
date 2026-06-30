-- Baseline migration: the RPG-system config schema (rpg_systems + 7 child
-- tables) that replaced config/topic_spine*.yaml, config/style_rules*.yaml,
-- and config/reference_sources*.yaml. See docs/RPG_SYSTEMS.md.
--
-- This file mirrors bin/core/db_schema.sql, which was applied directly via
-- the Supabase SQL Editor against the live project before this migrations/
-- folder existed. It's written here, idempotently (IF NOT EXISTS / DO
-- blocks), so the repo's migration history matches what's actually live,
-- and so it's safe to (re)run by hand if needed. Data was backfilled
-- separately via bin/core/migrate_config_to_db.py -- this file is schema
-- only, matching standard Supabase migration convention.

CREATE TABLE IF NOT EXISTS rpg_systems (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  chain_tag TEXT NOT NULL,
  path_suffix TEXT NOT NULL DEFAULT '',
  is_active BOOLEAN NOT NULL DEFAULT true,
  ruleset TEXT,
  target_seconds INT DEFAULT 55,
  reading_level TEXT DEFAULT 'general',
  no_homebrew_mechanics BOOLEAN DEFAULT true,
  default_length TEXT DEFAULT 'shorts',
  spice_rate REAL DEFAULT 0.0,
  persona_default TEXT DEFAULT 'table_coach',
  voiceover_default_voice_pack_id TEXT,
  voiceover_default_tts_voice_id TEXT,
  active_srd_path TEXT,
  srd_pdf_path TEXT,
  reference_sources JSONB,
  bg_image_prompt_prefix TEXT DEFAULT '',
  bg_image_prompt_suffix TEXT DEFAULT '',
  music_prompt_prefix TEXT DEFAULT '',
  music_prompt_suffix TEXT DEFAULT '',
  enable_ai BOOLEAN DEFAULT false,
  enable_ai_script BOOLEAN DEFAULT false,
  enable_tts BOOLEAN DEFAULT false,
  enable_bg_image BOOLEAN DEFAULT false,
  enable_bg_music BOOLEAN DEFAULT false,
  enable_pdf_flavor BOOLEAN DEFAULT false,
  tts_voice_variety_lookback_days INT DEFAULT 7,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS system_weekly_spine (
  system_id TEXT NOT NULL REFERENCES rpg_systems(id) ON DELETE CASCADE,
  day_of_week TEXT NOT NULL CHECK (day_of_week IN ('mon','tue','wed','thu','fri','sat','sun')),
  category TEXT NOT NULL,
  PRIMARY KEY (system_id, day_of_week)
);

CREATE TABLE IF NOT EXISTS system_categories (
  id SERIAL PRIMARY KEY,
  system_id TEXT NOT NULL REFERENCES rpg_systems(id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  persona TEXT,
  tones TEXT[],
  voices TEXT[] NOT NULL,
  angles TEXT[] NOT NULL,
  UNIQUE(system_id, category)
);

CREATE TABLE IF NOT EXISTS system_category_angle_weights (
  id SERIAL PRIMARY KEY,
  system_id TEXT NOT NULL REFERENCES rpg_systems(id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  angle TEXT NOT NULL,
  weight INT NOT NULL DEFAULT 1,
  UNIQUE(system_id, category, angle)
);

CREATE TABLE IF NOT EXISTS system_tones (
  id SERIAL PRIMARY KEY,
  system_id TEXT NOT NULL REFERENCES rpg_systems(id) ON DELETE CASCADE,
  tone TEXT NOT NULL,
  voice_pack_id TEXT,
  tts_voice_ids TEXT[],
  UNIQUE(system_id, tone)
);

CREATE TABLE IF NOT EXISTS system_voices (
  id SERIAL PRIMARY KEY,
  system_id TEXT NOT NULL REFERENCES rpg_systems(id) ON DELETE CASCADE,
  voice_name TEXT NOT NULL,
  tts_voice_ids TEXT[],
  hooks TEXT[] NOT NULL,
  ctas TEXT[] NOT NULL,
  UNIQUE(system_id, voice_name)
);

CREATE TABLE IF NOT EXISTS system_voice_category_lines (
  id SERIAL PRIMARY KEY,
  system_id TEXT NOT NULL,
  voice_name TEXT NOT NULL,
  category TEXT NOT NULL,
  hooks TEXT[],
  ctas TEXT[],
  FOREIGN KEY (system_id, voice_name) REFERENCES system_voices(system_id, voice_name) ON DELETE CASCADE,
  UNIQUE(system_id, voice_name, category)
);

CREATE TABLE IF NOT EXISTS system_personas (
  id SERIAL PRIMARY KEY,
  system_id TEXT NOT NULL REFERENCES rpg_systems(id) ON DELETE CASCADE,
  persona TEXT NOT NULL,
  one_liner TEXT,
  UNIQUE(system_id, persona)
);

CREATE INDEX IF NOT EXISTS idx_system_categories_system ON system_categories(system_id);
CREATE INDEX IF NOT EXISTS idx_system_angle_weights_system_cat ON system_category_angle_weights(system_id, category);
CREATE INDEX IF NOT EXISTS idx_system_voices_system ON system_voices(system_id);
CREATE INDEX IF NOT EXISTS idx_system_voice_lines_system_voice ON system_voice_category_lines(system_id, voice_name);

-- RLS: enabled on every table so the public PostgREST API (anon/authenticated
-- keys) can't read this data. No policies are added, since the pipeline only
-- ever connects directly as the postgres role via BIZZAL_DB_URL, which
-- bypasses RLS entirely. If a future form UI needs to read/write this via
-- the REST API instead of a direct DB connection, add scoped policies then.
DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'rpg_systems', 'system_weekly_spine', 'system_categories',
    'system_category_angle_weights', 'system_tones', 'system_voices',
    'system_voice_category_lines', 'system_personas'
  ]
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
  END LOOP;
END $$;
