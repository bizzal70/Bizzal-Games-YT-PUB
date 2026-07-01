# Bizzal-Games-YT-PUB — Session State 2026-06-30

## What we are working on

Getting the AI-generated script body to read as dry, specific mechanical observations —
not scenes, not narration, not vague generalizations. The "It's Already When" RTFM voice:
assume the viewer read the manual, tell them what it means in practice.

**Target tone (write like this):**
> "Acid Splash hits two targets if they share a square. Most players aim for isolated
> enemies and waste the AoE. Stack a Sleet Storm first and the clump happens for you."

**NOT this (what it was doing):**
> "Picture this: your party is cornered in a narrow stone corridor. Two goblins squabbling
> over a shiny trinket, oblivious to the approaching doom..."

---

## Changes pushed this session (all on main)

### 1. AI Script Model — `gpt-4o`
- `daily.yml` — added `BIZZAL_OPENAI_MODEL: "gpt-4o"`
- Was defaulting to `gpt-4o-mini`, which couldn't follow the specificity rules

### 2. AI Script Prompt Rewrite — `bin/core/write_script_from_fact.py`
**System prompt:** Killed the "veteran DM telling stories" identity. Now:
"making observations. No scenes, no characters, no narration. Think senior engineer
in a code review, not a dungeon master telling campfire stories."

**Task:** Removed "scenario-first". Now: dry mechanical observation, no scenes, no
characters, state what players consistently get wrong, what smart play looks like.

**Body rule:** Explicit BAD/GOOD example. Every sentence must name a specific mechanic,
number, or condition from `fact_mechanics`. Banned "players often overlook the strategic
advantage" style vagueness by name.

**Anti-theatrical:** No "Picture this", "Who knew", "Watch as", "It's about the story".

**Temperature:** 0.45

### 3. fact_mechanics injection — `bin/core/write_script_from_fact.py`
**Root cause of vagueness:** AI had no actual data. Only got `fact_name` and `kind`.
Now gets full raw DB fields injected as `fact_mechanics`:
- Spells: tier, concentration, duration, range, damage_roll, saving_throw, classes, etc.
- Creatures: lv, ac, hp, attacks, ability scores, alignment, talents
- Items: rarity, requires_attunement, bonus, benefit, curse
- Rules: desc (truncated 300 chars)
- Classes: hit_dice, caster_type, primary_abilities, key_talent

Applies to BOTH `maybe_ai_polish_script()` and `maybe_ai_polish_cta()`.
Applies to ALL categories and ALL RPG systems automatically.

### 4. Permanent content dedup — `bin/core/fill_picks.py`
**Problem:** Validated atoms are ephemeral (runner temp). The 14-day PK lookback was
finding nothing — same topic could repeat.

**Fix:** Added `registry_used_fact_names()` which reads
`data/state/published_registry_{SYSTEM_ID}.json` (committed back to repo after each run).
Permanent avoid-by-name across all categories. No topic ever repeats regardless of age.

### 5. Shadowdark reference data enriched
**Problem:** `reference/systems/shadowdark/active/*.json` only had `name` + `document`.
AI had zero mechanics to cite for Shadowdark content.

**Fix:** Wrote `C:/CLAUDE CODE/enrich_shadowdark_fixtures.py` (local on John's machine).
Parses `C:/GAMEPUB/SHADOWDARK/Shadowdark_RPG_-_V4-8.pdf` and outputs enriched fixtures.

**Pushed to repo:**
| File | Count | Key fields |
|---|---|---|
| `Spell.json` | 70 | tier, range, duration, classes |
| `Creature.json` | 228 | lv, ac, hp, attacks, all ability mods, alignment, talents |
| `Item.json` | 104 | bonus, benefit, curse |
| `Rule.json` | 12 | core mechanics |
| `CharacterClass.json` | 4 | Fighter/Priest/Thief/Wizard |

---

## Status of AI tone fix — UNVERIFIED

The last test run (28496188538) used the OLD prompt (before fact_mechanics).
The new prompt + fact_mechanics was pushed AFTER that run completed.
A fresh run was NOT triggered before saving.

**First thing tomorrow:** Trigger a test run and read the body from the registry:

```bash
gh workflow run daily.yml --repo bizzal70/Bizzal-Games-YT-PUB \
  -f systems=all -f privacy=unlisted -f dry_run=false

# After it completes (~5 min), read the result:
gh api repos/bizzal70/Bizzal-Games-YT-PUB/contents/data/state/published_registry_dnd5e.json \
  --jq '.content' | base64 -d | python3 -c "
import json,sys
d=json.load(sys.stdin)
items = d if isinstance(d,list) else d.get('items',[])
fp = items[-1]['fingerprint']
print('FACT:', fp['fact_name'])
print('HOOK:', fp['hook'])
print('BODY:', fp['body'])
print('CTA:', fp['cta'])
"
```

Check: does the body name specific mechanics/numbers? No scenes? No characters?
If yes — tone is locked. If no — escalate the body rule further.

---

## Key files to know

| File | Purpose |
|---|---|
| `bin/core/write_script_from_fact.py` | AI script polish — prompt, rules, fact_mechanics |
| `bin/core/fill_picks.py` | Fact selection + permanent dedup |
| `bin/core/pick_style.py` | Tone/angle/voice with 5-day lookback |
| `bin/core/run_daily_cloud_cron.sh` | Loops over all active systems |
| `.github/workflows/daily.yml` | Env vars, model config |
| `data/state/published_registry_*.json` | Permanent content log per system |
| `reference/systems/shadowdark/active/` | Enriched Shadowdark fixtures |
| `assets/brand/channel_icon.png` | Circular PNG overlay, top-right corner |

---

## Local files (John's machine only)

| Path | Purpose |
|---|---|
| `C:/GAMEPUB/SHADOWDARK/Shadowdark_RPG_-_V4-8.pdf` | Full Shadowdark core (740pp) |
| `C:/GAMEPUB/SHADOWDARK/SoloDark_V1_(PDF).pdf` | SoloDark supplement (87pp, not yet parsed) |
| `C:/CLAUDE CODE/enrich_shadowdark_fixtures.py` | PDF parser script |
| `C:/CLAUDE CODE/shadowdark_fixtures/` | Last generated fixture output |

---

## The pipeline at a glance

```
GitHub Actions (daily.yml)
  └─ run_daily_cloud_cron.sh  (loops each active system)
       └─ make_atom.py         (pick category + angle)
       └─ fill_picks.py        (pick fact, dedup vs registry)
       └─ pick_style.py        (tone/voice/spice)
       └─ attach_fact.py       (load fact fields from SRD JSON)
       └─ write_script_from_fact.py  (build base script + AI polish)
       └─ synthesize_tts.py    (OpenAI TTS, onyx, 0.9x)
       └─ render_atom.sh       (ffmpeg: bg image + music + TTS + icon overlay)
       └─ upload_youtube.py    (OAuth2 upload)
       └─ published_registry_*.json  (committed back)
```

Systems: dnd5e, shadowdark (both active, both run daily with `BIZZAL_CLOUD_SYSTEMS=all`)