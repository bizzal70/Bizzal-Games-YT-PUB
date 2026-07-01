# Adding content: systems, collections (modules/supplements), and themes

Companion to [RPG_SYSTEMS.md](RPG_SYSTEMS.md). That doc covers registering a **system**
(the DB rows). This doc covers the part that actually governs output quality: getting a
source's **mechanical reference data** into a shape the pipeline can use — and tagging it
so one system can hold many **collections** (core rules, supplements/modules, or your own
themes) that products can slice by.

## The three ingestion flows

| Flow | What it is | What it touches |
|---|---|---|
| **A. New system** | Its own rules (e.g. DCC, a Year Zero game) | `system_*` DB rows (see RPG_SYSTEMS.md) **+** a fresh reference corpus |
| **B. Content pack / module** | Same rules, extra themed content (e.g. Shadowdark *Cursed Scroll* issues, a D&D module) | **Only** reference fixtures — append `document`-tagged records to the system's existing category files |
| **C. Theme** | A vibe you assemble yourself (e.g. `gothic-horror` from SRD-legal + original content) | Same as B — it's just a `document` value you coin |

B and C need **no new system and no code changes** beyond an optional collection filter (below).
That's the payoff of the existing `document` field.

## The reference fixture format (what enrichment must produce)

Each category is one JSON file, an array of Django-style fixture records:

```json
[
  {
    "model": "srd.creature",
    "pk": 231,
    "fields": {
      "name": "Strahd-style Vampire Lord",
      "document": "gothic-horror",
      "lv": 15, "ac": 17, "hp": 144,
      "attacks": "2 slam +9 (2d6+4) or bite ...",
      "movement": "30 ft, climb 30 ft",
      "ability_score_strength": 18, "ability_score_dexterity": 18,
      "ability_score_constitution": 18, "ability_score_intelligence": 17,
      "ability_score_wisdom": 15, "ability_score_charisma": 18,
      "alignment": "Chaotic Evil",
      "talents": "Regeneration; Charm; children of the night ..."
    }
  }
]
```

- `document` = the **collection tag** (e.g. `shadowdark-core`, `cursed-scroll-1`, `gothic-horror`). Every record MUST have one.
- `pk` = unique integer **within its file**. When appending a pack, start at `max(existing pk) + 1`.
- Files live under the system's `active_srd_path` dir (convention: `reference/<system>/active/<Category>.json`). The DB `reference_sources.sources` block maps category → file (`creatures`→`Creature.json`, etc.).

**Required per category** (the more mechanical fields, the more specific the AI copy — thin data → thin bodies):

| Category | file | fields beyond `name` + `document` |
|---|---|---|
| creatures | `Creature.json` | `lv, ac, hp, attacks, movement, ability_score_{str,dex,con,int,wis,cha}, alignment, talents` |
| spells | `Spell.json` | `tier, range_text, duration, classes, desc` |
| items | `Item.json` | `bonus, benefit, curse, desc` |
| rules | `Rule.json` | `desc` (+ any core-mechanic fields) |
| classes | `CharacterClass.json` | `hit_dice, weapons, armor, primary_abilities, key_talent, caster_type` |

(`desc` and `document` are stripped before the AI sees `fact_mechanics`; they're kept for provenance.)

## Collection scoping (the one small code change B/C want)

`fill_picks.py` currently picks across **all** records in a category file, regardless of
`document`. To run a stream scoped to a collection (e.g. a "Cursed Scroll 1" series or a
"Gothic Horror" week), add an optional filter: when `BIZZAL_COLLECTION` (or an atom field)
is set, keep only records whose `fields.document` is in the allowed set before picking.
~5 lines in each `pick_*` path. Leave unset → current behavior (whole corpus).

## Registry gap for products (small, do when the zine work starts)

The publish registry fingerprint stores `fact_kind`/`fact_pk`/`fact_name` but **not**
`document`. Add `document` to the fingerprint (the fact already carries it via
`attach_fact.py`) so monthly zines/bundles can slice output by collection. Until then,
collection can be back-derived from `fact_pk` + the fixtures.

## Enrichment: reusable half vs. bespoke half

Turning a raw product (PDF, SRD JSON, CSV) into these fixtures splits cleanly:

- **Bespoke (you write per source):** parse the raw layout into a list of plain dicts.
  Every product's layout differs; this can't be fully generic. `enrich_shadowdark_fixtures.py`
  is a worked PDF example.
- **Reusable (`enrich_source.py`):** takes those normalized dicts + a `--document` tag,
  maps them to the fixture schema for the category, assigns append-safe pks, tags them,
  merges into the target file, and validates. This is the boring, error-prone part — done once.

So the per-source cost is just "parse raw → normalized dicts"; everything downstream is shared.

## Add-a-content-pack checklist (flow B/C)

1. Get the source content into normalized dicts (bespoke parser) — one list per category.
2. `enrich_source.py --system <id> --category <cat> --document <tag> --input normalized.json`
   → appends tagged, pk-assigned fixtures into `reference/<system>/active/<Category>.json`.
3. Validate (the script does; also `python -m json.tool` the file).
4. (Optional) add the collection filter to `fill_picks.py` if you want a scoped stream.
5. Smoke test: `bin/core/run_daily_diag_for_system.sh <system_id>` (optionally with the
   collection set) and read the generated body.

## Licensing gate (per collection — verify, NOT legal advice)

Before ingesting a source you intend to publish/sell from, confirm you may republish it:
- **SRD rules** (D&D 5.1 SRD = CC-BY) → yes, with attribution.
- **Named settings/adventures** (Curse of Strahd, Ravenloft) = WotC Product Identity, NOT SRD →
  DMs Guild lane only. Prefer **themes you build** (`gothic-horror`) over named IP.
- **Shadowdark** = permissive 3rd-party license for *compatible* content; the specific
  content of *Cursed Scroll* products is The Arcane Library's IP — "compatible/commentary" OK,
  "republish their statblocks verbatim" needs care.
- **Free League**: line-by-line (Alien/One Ring = locked; their own lines often have terms).
- Rule of thumb: **theme = your IP; named product content = licensed lane.**
