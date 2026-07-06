-- Migration 0001: Baseline schema
-- Source: bin/core/db_schema.sql
-- Applied: 2026-07-01 (initial Supabase setup)
-- Do NOT re-run against a live DB -- tables already exist.
-- To reset: DROP all tables and re-run this + 0002.

-- RPG-system config schema. Run once against the Supabase Postgres DB to set
-- up the tables that replace config/topic_spine*.yaml, config/style_rules*.yaml,
-- and config/reference_sources*.yaml. See docs/RPG_SYSTEMS.md for how to add
-- a new system once this is in place.

CREATE TABLE IF NOT EXISTS rpg_systems (
  id TEXT PRIMARY KEY,                  -- 'dnd5e', 'shadowdark'
  display_name TEXT NOT NULL,
  chain_tag TEXT NOT NULL,              -- shown in Discord messages, e.g. 'D&D'
  path_suffix TEXT NOT NULL DEFAULT '', -- '' keeps the existing data/atoms/ layout; '_shadowdark' etc for others
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
  reference_sources JSONB,              -- nested sources.* block (creatures/spells/items/etc with joins); kept for provenance, not read by the core pipeline beyond active_srd_path/srd_pdf_path above
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
  tones TEXT[],            -- null falls back to rpg_systems-level default tone list
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
  tts_voice_ids TEXT[],     -- optional per-voice override pool (only dnd5e uses this today)
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