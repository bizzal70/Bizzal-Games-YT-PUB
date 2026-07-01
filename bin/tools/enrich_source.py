#!/usr/bin/env python3
"""
enrich_source.py — the REUSABLE half of content ingestion for Bizzal Games Pub.

Turns already-normalized content records into pipeline-ready, `document`-tagged
reference fixtures and merges them into a system's category file. Works for BOTH
a brand-new system's corpus and appending a content pack / module / theme to an
existing system (flows A/B/C in docs/ADDING_CONTENT.md).

WHAT YOU WRITE PER SOURCE (bespoke — layouts differ): a tiny parser that turns the
raw product (PDF/CSV/SRD JSON) into a JSON array of plain dicts, each with the
fields listed in CATEGORY_SPEC[category]["fields"] (at minimum "name"). Extra keys
are ignored. See enrich_shadowdark_fixtures.py for a worked PDF example.

WHAT THIS DOES (reusable — done once): map those dicts to the fixture schema,
assign append-safe pks, stamp every record with `document`, merge into
reference/<system>/active/<Category>.json, and validate.

Usage:
    python enrich_source.py \
        --system shadowdark --category spells \
        --document cursed-scroll-1 \
        --input normalized_spells.json \
        --repo-root /path/to/Bizzal-Games-YT-PUB
    # dry run (validate + preview counts, write nothing):
    #   add --dry-run
    # brand-new file with no existing records needs a model string:
    #   add --model srd.spell
"""
import argparse
import json
import os
import sys

# category -> (target file, mechanical field allow-list). "name" is always kept;
# "document" is stamped by this script. Keep in sync with the reference fixtures
# and bin/core/fill_picks.py / attach_fact.py.
CATEGORY_SPEC = {
    "creatures": {
        "file": "Creature.json",
        "fields": [
            "name", "lv", "ac", "hp", "attacks", "movement",
            "ability_score_strength", "ability_score_dexterity",
            "ability_score_constitution", "ability_score_intelligence",
            "ability_score_wisdom", "ability_score_charisma",
            "alignment", "talents",
        ],
    },
    "spells": {
        "file": "Spell.json",
        "fields": ["name", "tier", "range_text", "duration", "classes", "desc"],
    },
    "items": {
        "file": "Item.json",
        "fields": ["name", "bonus", "benefit", "curse", "desc"],
    },
    "rules": {
        "file": "Rule.json",
        "fields": ["name", "desc"],
    },
    "classes": {
        "file": "CharacterClass.json",
        "fields": ["name", "hit_dice", "weapons", "armor",
                   "primary_abilities", "key_talent", "caster_type"],
    },
}


def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def next_pk(existing):
    pks = [r.get("pk") for r in existing if isinstance(r.get("pk"), int)]
    return (max(pks) + 1) if pks else 1


def infer_model(existing, category, cli_model):
    if cli_model:
        return cli_model
    for r in existing:
        if r.get("model"):
            return r["model"]
    raise SystemExit(
        f"ERROR: {category} target file has no existing records to infer 'model' from; "
        f"pass --model (e.g. --model srd.{category.rstrip('s')})."
    )


def to_fixture(category, norm, pk, document, model):
    allow = CATEGORY_SPEC[category]["fields"]
    fields = {}
    for k in allow:
        v = norm.get(k)
        if v is None or v == "" or v == []:
            continue
        fields[k] = v
    if not fields.get("name"):
        raise ValueError(f"record missing required 'name': {norm!r}")
    fields["document"] = document
    return {"model": model, "pk": pk, "fields": fields}


def enrich(repo_root, system, category, document, normalized, cli_model, dry_run):
    if category not in CATEGORY_SPEC:
        raise SystemExit(f"ERROR: unknown category '{category}'. "
                         f"Choices: {', '.join(CATEGORY_SPEC)}")
    active_dir = os.path.join(repo_root, "reference", system, "active")
    target = os.path.join(active_dir, CATEGORY_SPEC[category]["file"])
    existing = load_json(target)
    model = infer_model(existing, category, cli_model)

    # Dedup by name across the WHOLE file (any collection), so ingesting a pack
    # never re-adds core content and re-running is idempotent. If a supplement
    # legitimately needs a same-named-but-different entry, disambiguate the name.
    existing_names = {
        (r.get("fields") or {}).get("name", "").strip().lower()
        for r in existing
    }
    pk = next_pk(existing)
    added, skipped = [], []
    for norm in normalized:
        name = str(norm.get("name") or "").strip()
        if not name:
            skipped.append(norm); continue
        if name.lower() in existing_names:
            skipped.append(name); continue           # already present in this collection
        added.append(to_fixture(category, norm, pk, document, model))
        existing_names.add(name.lower())
        pk += 1

    merged = existing + added
    problems = validate(merged)
    if problems:
        raise SystemExit("ERROR: validation failed:\n  " + "\n  ".join(problems))

    print(f"[enrich] {system}/{category} doc={document}: "
          f"+{len(added)} new, {len(skipped)} skipped (dupes/blank), "
          f"total now {len(merged)} (model={model})")
    if dry_run:
        print("[enrich] --dry-run: nothing written")
        return
    os.makedirs(active_dir, exist_ok=True)
    atomic_write(target, merged)
    print(f"[enrich] wrote {target}")


def validate(records):
    problems, seen_pks = [], set()
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            problems.append(f"[{i}] not an object"); continue
        if not r.get("model"):
            problems.append(f"[{i}] missing 'model'")
        pk = r.get("pk")
        if not isinstance(pk, int):
            problems.append(f"[{i}] pk not an int: {pk!r}")
        elif pk in seen_pks:
            problems.append(f"[{i}] duplicate pk: {pk}")
        else:
            seen_pks.add(pk)
        fields = r.get("fields") or {}
        if not str(fields.get("name") or "").strip():
            problems.append(f"[{i}] missing fields.name")
        if not str(fields.get("document") or "").strip():
            problems.append(f"[{i}] missing fields.document")
    return problems


def main():
    ap = argparse.ArgumentParser(description="Merge normalized records into pipeline fixtures.")
    ap.add_argument("--system", required=True, help="system id, e.g. shadowdark / dnd5e / dcc")
    ap.add_argument("--category", required=True, choices=list(CATEGORY_SPEC))
    ap.add_argument("--document", required=True, help="collection tag, e.g. cursed-scroll-1")
    ap.add_argument("--input", required=True, help="JSON array of normalized dicts")
    ap.add_argument("--repo-root", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    ap.add_argument("--model", default="", help="fixture model string (needed only for a brand-new file)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    normalized = load_json(args.input)
    if not isinstance(normalized, list):
        raise SystemExit("ERROR: --input must be a JSON array of objects")
    enrich(args.repo_root, args.system, args.category, args.document,
           normalized, args.model, args.dry_run)


if __name__ == "__main__":
    main()
