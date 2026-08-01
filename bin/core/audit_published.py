#!/usr/bin/env python3
"""
audit_published.py -- fact-check published content against the SRD corpus.

Two checks per item:
  1. DETERMINISTIC grounding (trustworthy): is the item's fact_name a real entity
     in reference/systems/<sys>/active/* ? Order-independent token match, run
     against the FULL local fixtures (incl. ingested expansions). This is the
     arbiter that may drive action.
  2. ADVISORY canon check (content_safety.canon_check): an LLM accuracy read
     grounded in the SRD digest. Unreliable on niche/expansion content (it
     false-positives on real zine classes like "Desert Rider"), so it is shown
     for review only -- never a standalone verdict.

Clips (tier=="clip") are excluded from check 1: make_clips_from_longform.py stores
the clip's hook sentence in fact_name, not an entity name (fact_pk is null), so the
token match was comparing a whole sentence against single-entity fixture names and
false-flagging real clips (confirmed: 8 of 17 published clips false-flagged, incl.
real content like Hellhound and Black Pudding). Cross-referencing to the parent
long-form video's fact_name was considered but long-form entries frequently have an
empty fact_name too (a long-form script can synthesize multiple facts, not one
entity), so there is no reliable entity name to check clips against -- check 1 is
skipped for clips (det=None) rather than checking the wrong thing. Checks against
IP hits and the advisory canon check still run for clips.

Confabulated content shows up as IP hits or NOT-IN-FIXTURES; those are the hard
flags. A canon-only flag is a "human, double-check this one" note.

Usage: python bin/core/audit_published.py [--day YYYY-MM-DD] [--all]
Needs BIZZAL_OPENAI_API_KEY (canon) + BIZZAL_DB_URL (srd path) for full output;
the deterministic check works without them.
"""
import os, sys, json, re, ast, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import content_safety

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
STATE = os.path.join(REPO_ROOT, "data", "state")
LABEL = {"dnd5e": "D&D 5e (2024 rules)", "shadowdark": "Shadowdark RPG",
         "dcc": "Dungeon Crawl Classics RPG"}
KINDS = ["CharacterClass", "Species", "Background", "Feat", "Item", "Spell",
         "Rule", "Creature", "Weapon", "Armor"]


def toks(s):
    return frozenset(re.findall(r"[a-z0-9]+", (s or "").lower()))


def load_json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def fixture_tokensets(sysid):
    out = []
    base = os.path.join(REPO_ROOT, "reference", "systems", sysid, "active")
    for k in KINDS:
        data = load_json(os.path.join(base, k + ".json"))
        if isinstance(data, list):
            for rec in data:
                f = rec.get("fields", rec) if isinstance(rec, dict) else {}
                nm = f.get("name") or f.get("title")
                if nm:
                    out.append(toks(nm))
    return out


def grounded_name(name, tsets):
    ft = toks(name)
    if not ft:
        return True
    for nt in tsets:
        if ft == nt or ft <= nt or nt <= ft:
            return True
        if len(ft & nt) >= 2 and len(ft & nt) >= len(ft) - 1:
            return True
    return False


def fp_of(it):
    fp = it.get("fingerprint")
    if isinstance(fp, str):
        try:
            fp = ast.literal_eval(fp)
        except Exception:
            fp = {}
    return fp if isinstance(fp, dict) else {}


def item_text(it, fp):
    parts = [fp.get("hook") or it.get("hook", ""),
             fp.get("body") or it.get("body", ""),
             fp.get("cta") or it.get("cta", "")]
    return "\n".join(p for p in parts if p).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    day = a.day.strip()

    tsets = {s: fixture_tokensets(s) for s in LABEL}
    digests = {s: content_safety.srd_digest(s, REPO_ROOT) for s in LABEL}

    def want(d):
        return a.all or not day or d == day

    rows = []

    def audit_item(sysid, tier, vid, name, text):
        if not vid:
            return
        ip_ok, hits = content_safety.scan_text(f"{name}\n{text}")
        # Clips store the hook sentence in fact_name, not an entity name -- see
        # module docstring. The deterministic entity-name check does not apply.
        det = grounded_name(name, tsets[sysid]) if (name and tier != "clip") else None
        v = content_safety.canon_check(text, LABEL[sysid], reference=digests[sysid]) if text else None
        rows.append({"sys": sysid, "tier": tier, "vid": vid, "name": name,
                     "ip_ok": ip_ok, "ip": hits, "det": det,
                     "canon": (v.grounded if v and v.available else None),
                     "verdict": (v.verdict if v and v.available else "")})

    for s in LABEL:
        for tier, fn in (("short", f"published_registry_{s}.json"),
                         ("clip", f"published_registry_clips_{s}.json"),
                         ("long", f"published_registry_longform_{s}.json")):
            reg = load_json(os.path.join(STATE, fn)) or {}
            items = reg.get("items", reg) if isinstance(reg, dict) else reg
            for it in (items or []):
                if not want(it.get("day", "")):
                    continue
                fp = fp_of(it)
                audit_item(s, tier, it.get("youtube_video_id", ""),
                           fp.get("fact_name") or it.get("fact_name", ""),
                           item_text(it, fp))

    ig = load_json(os.path.join(STATE, "published_registry_instagram.json")) or {}
    for it in (ig.get("items", ig) if isinstance(ig, dict) else ig) or []:
        if not want(it.get("day", "")):
            continue
        s = it.get("system", "")
        if s not in LABEL:
            continue
        text = "\n".join(x for x in [it.get("hook", ""), it.get("body", ""), it.get("cta", "")] if x)
        audit_item(s, "IG", it.get("instagram_post_id", ""), it.get("fact_name", ""), text)

    scope = "ALL" if a.all else (day or "today")
    print(f"AUDIT scope={scope}: {len(rows)} items\n" + "=" * 72)
    hard = [r for r in rows if (not r["ip_ok"]) or (r["det"] is False)]
    for r in rows:
        flags = []
        if not r["ip_ok"]:
            flags.append(f"IP:{r['ip']}")
        if r["det"] is False:
            flags.append("NOT-IN-FIXTURES")
        if r["canon"] is False:
            flags.append("canon-note(advisory)")
        mark = "FLAG" if ((not r["ip_ok"]) or r["det"] is False) else ("note" if r["canon"] is False else "ok")
        print(f"[{mark:4}] {r['sys']}/{r['tier']} {r['vid']} {r['name']!r} {' '.join(flags)}")
        if r["canon"] is False and mark != "FLAG":
            print(f"         advisory: {r['verdict']}")
    print("=" * 72)
    print(f"HARD FLAGS (IP or not-in-fixtures -> real confabulation signal): {len(hard)}")
    if hard:
        print("UNLIST_CANDIDATES=" + ",".join(r["vid"] for r in hard))


if __name__ == "__main__":
    main()
