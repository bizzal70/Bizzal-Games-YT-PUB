# Content Integrity — postmortem, defenses, and runbook

Reference for why bad AI content reached the channels, what stops it now, and how
to audit/repair going forward. Written 2026-07-22 after the "Godzilla in D&D"
incident. Keep this current when the pipeline changes.

---

## TL;DR

- **Root cause:** the long-form pipeline takes *news headlines* and asks an LLM to
  *write rules*. With no grounding data the model confidently invents. The Shorts
  pipeline never had this problem because every Short is generated **from a real
  SRD fact** (`fact_pk`) — grounded by construction.
- **Blast radius:** every one of the 8 published long-forms was confabulated (not
  just Godzilla). All confabulated long-form + clips are unlisted.
- **The fix (chosen):** ground long-form generation in the SRD corpus the same way
  Shorts already are. Public sources may seed *which* real topic to cover, but the
  subject and every mechanic must come from `reference/systems/<sys>/active/*`.
- **Hard lesson about auto-fact-checking:** an LLM judge — even grounded — is too
  unreliable on fine mechanics/stat-blocks to auto-unlist. It false-positived on
  real content (said "Ancient Gold Dragon is not in D&D 5e"; "Alter Self doesn't
  use concentration"; "Luck Tokens don't exist in Shadowdark"). Use it as an
  **advisory signal only**; the reliable arbiter is deterministic fixture grounding.

---

## What happened

| Date | Content | Failure | Status |
|---|---|---|---|
| 2026-07-22 | "Godzilla in D&D 5e" long-form `Spsl-LoNlSU` + 3 clips | third-party IP + invented statblock | unlisted |
| 2026-07-20 | "Shadowdark Summoner" long-form `BHX0I5dEuys` + clips | Summoner is a **Daggerheart** class, not Shadowdark | unlisted |
| 2026-07-16..18 | 6 DCC long-forms (Deathbringer, "Clown class", vintage spells) | invented DCC items/classes; non-DCC products as official | unlisted (4 live; 7 were already-deleted test uploads) |

All three trace to the same mechanism: the **topic scout** (`bin/longform/topic_scout.py`)
mapped an unrelated trending headline onto one of our systems, and
`write_longform_script.py` invented rules to fill the brief.

## Root cause analysis

1. **Scout had no guardrail.** It fed GPT-4o raw headlines ("Godzilla comes to
   Marvel Multiverse Roleplaying", "Daggerheart Summoner playtest") and asked for
   briefs "anchored to what the community is talking about." Any headline →
   a brief on one of our systems.
2. **Generator is ungrounded.** `load_fixture_sample()` loads SRD entries as
   *context only*; when nothing matches it literally prompts `(no fixture data)`
   and the model invents. Nothing enforces that the subject exists in the system.
3. **The quality gate makes it worse, not better.** `bin/core/script_quality.py`
   scores *writing quality* and its rubric rewards "EVERY sentence must carry a
   specific mechanic/number." A confident fabrication scores **high** and passes.
   It also fails **open** (API down ⇒ everything passes).
4. **Shorts were fine the whole time** because they start from a real `fact_pk`
   (e.g. `srd-2024_gold-dragon-wyrmling`) pulled from the fixtures. Grounding is
   the entire difference.

## Defenses in place now

| Layer | File / where | What it does | Reliability |
|---|---|---|---|
| Scout guard | `topic_scout.py` `brief_is_safe()` | drops briefs naming third-party IP or other game systems; hardened prompt | deterministic, high |
| Shared safety module | `bin/core/content_safety.py` | single source of truth: `_BLOCKED_TERMS`, `scan_text()`, `srd_digest()`, `canon_check()` | mixed (see below) |
| IP hard-block | `make_longform_atom.py` → `content_safety.scan_text()` | scans final title+body; a "Godzilla" script goes to `failed/`, never publishes | deterministic, high |
| Unlisted-until-verified | `longform_daily.yml` (`|| 'unlisted'`) | scheduled long-form uploads **unlisted**, not public | high |
| Orphan fix | `make_longform_atom.py` | a blocked/failed brief is marked `failed`, not stuck `in_progress` forever | — |
| Canon fact-check | `content_safety.canon_check()` (SRD-grounded) | LLM checks a script against the real corpus digest | **advisory only** |

### Why `canon_check` is advisory, not an auto-unlister

Grounded in the SRD digest it still produced false positives on real content
(niche/zine mechanics, exact stat-blocks it can't recall). Concrete misfires
observed: flagged the *Ancient Gold Dragon*, *Alter Self* concentration, and
*Gold Dragon Wyrmling*'s amphibious trait as "fabrication" — all real. So:

- **Deterministic checks decide.** Fixture membership (does `fact_name`/`fact_pk`
  resolve to `reference/systems/<sys>/active/*`?) and the IP denylist are the
  arbiters that may act automatically.
- **`canon_check` only advises** — surface its flags for human review; never
  auto-unlist on it alone. Note the fixtures are an SRD **subset**, so
  "not in fixtures" ≠ "fake" (real Monster-Manual dragons aren't in the SRD).

## Going-forward architecture (the real fix)

Ground long-form like Shorts:
1. Pick the subject from `reference/systems/<sys>/active/*` (rotate kinds; track
   used entities in state) — not from the news.
2. Feed the entity's real fields as source-of-truth; instruct the model to explain
   only what's supported (interactions, edge cases, common misplays) and never
   invent items/subclasses/mechanics.
3. Public sources may influence *which real topic* is chosen; news that isn't a
   rule becomes commentary, never invented rules.
4. Backstop with `canon_check` (grounded) + the IP scan + quality gate.
5. Re-enable auto-public only after a dry-run proves accuracy on real fixtures.

## Runbook

### Where facts come from (verified)
The runtime fact source for Shorts/IG is the committed **`reference/systems/<sys>/active/*.json`**
files. `bin/core/attach_fact.py` → `resolve_active_srd_path` → `load_json(base_path)`
→ `index_by_pk().get(pk)`. There is **no umbrel and no DB** in the fact path
(`sync_reference_from_umbrel.sh` is dormant; `BIZZAL_DB_URL` is only the
content-ledger/dedup store). These fixtures include ingested expansions
(e.g. Shadowdark Cursed Scroll vols; see `source_registry.json`). Every Short/IG
post carries a real `fact_pk`, so its subject is grounded by construction.

### Audit published content
- Deterministic (trustworthy): for each registry item, check `fact_name` membership
  in the union of `reference/systems/<sys>/active/*.json` names using
  **order-independent token matching** (fixtures store inverted names like
  "Golem, Iron"; see `attach_fact._deinvert_name`).
  **Load large fixtures via the raw media type**, not the contents API — files
  over ~1MB (D&D `Creature.json`, `Item.json`) return EMPTY from
  `contents --jq .content`, which will silently make every creature/item look
  "ungrounded". Use `gh api <path> -H "Accept: application/vnd.github.raw"` or the
  git blobs API.
- Advisory (LLM): `content_safety.canon_check(text, label, reference=srd_digest(sys, repo))`.
  Read the `problems`; do not auto-act.

### Unlist bad videos (safe pattern)
A one-shot `workflow_dispatch` job on `main` that:
1. materializes `secrets.BIZZAL_YT_TOKEN_JSON` to `.secrets/youtube_token.json`,
2. builds the YouTube client (scopes incl. `youtube.force-ssl`),
3. `videos().list(part=status)` the **exact** target IDs, **dry-run** prints
   current privacy, then `execute=true` flips public→unlisted preserving the other
   status fields (`selfDeclaredMadeForKids`, `license`, `embeddable`, `publicStatsViewable`),
4. delete the workflow after. Always target explicit IDs; always dry-run first.

### Instagram
The IG Graph API (Content Publishing) is **publish-only** — no delete/archive
endpoint. IG audits produce a review list only; removals are manual in-app.

## Gotchas learned (save future debugging time)

- **Scheduled-run env fallback.** `${{ github.event.inputs.privacy || 'public' }}`
  fell through to `public` on *scheduled* runs (inputs are empty then), even though
  the manual-dispatch default was `unlisted`. Check the fallback, not the input default.
- **GitHub contents API + Windows = CRLF.** Pushing from Windows lands `\r\n`,
  which breaks git rebase on the Linux runner and shell scripts. Assert
  `b'\r\n' not in data` before every push.
- **Bash heredoc eats backslashes.** In this environment a `<<'PY'` heredoc
  collapsed a typed `\\b` to a single `\b`, which Python wrote as a literal `0x08`
  backspace byte into a regex. Build such bytes via `bytes([0x5c, 0x62])` and verify
  with `repr()` + `b'\x08' not in data` before pushing.
- **Brief-orphan bug.** `pop_next_brief` only picks `status == "pending"`. Any code
  path that pops a brief (→ `in_progress`) then exits without marking it must reset
  it, or the brief is stranded forever.
- **Quality ≠ truth.** A quality/voice judge rewards confident specificity, which is
  exactly what a good fabrication has. Accuracy needs a *separate, grounded* check.
- **GitHub contents API truncates >1MB files.** `contents --jq .content` returns
  empty for files over ~1MB (no error). An audit that reads fixtures this way will
  silently treat all large-file content as missing. Use the raw media type / git
  blobs API. (This produced a false "13 D&D shorts are ungrounded" result until caught.)
- **Don't infer live infra from a filename.** `sync_reference_from_umbrel.sh` in the
  tree does not mean umbrel is used — it isn't. Verify the actual runtime path in
  code before asserting a data source.
