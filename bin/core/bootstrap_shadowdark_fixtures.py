#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from pathlib import Path


def eprint(msg: str):
    print(msg, file=sys.stderr)


def load_pdf_text(pdf_paths: list[Path]) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise RuntimeError("Missing dependency: pypdf. Install with: python3 -m pip install pypdf") from exc

    chunks: list[str] = []
    for pdf in pdf_paths:
        if not pdf.is_file():
            continue
        try:
            reader = PdfReader(str(pdf))
            for page in reader.pages:
                txt = page.extract_text() or ""
                if txt.strip():
                    chunks.append(txt)
        except Exception as exc:
            eprint(f"WARN: failed reading PDF {pdf}: {exc}")

    return "\n".join(chunks)


def extract_known_terms(text: str, terms: list[str]) -> list[str]:
    if not text.strip():
        return []
    found: list[str] = []
    hay = " " + re.sub(r"\s+", " ", text.lower()) + " "
    for term in terms:
        needle = " " + term.lower().strip() + " "
        if needle in hay:
            found.append(term)
    return found


def unique_keep_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def to_fixture_records(model: str, names: list[str], document: str) -> list[dict]:
    out = []
    for i, name in enumerate(unique_keep_order(names), start=1):
        out.append(
            {
                "model": model,
                "pk": i,
                "fields": {
                    "name": name,
                    "document": document,
                },
            }
        )
    return out


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Shadowdark fixture JSON files from source PDFs.")
    parser.add_argument("--repo-root", default="", help="Repo root (default: auto from script location)")
    parser.add_argument(
        "--pdf-dir",
        default="reference/systems/shadowdark/source_pdfs",
        help="Directory containing Shadowdark PDF files",
    )
    parser.add_argument(
        "--out-dir",
        default="reference/systems/shadowdark/active",
        help="Output directory for fixture JSON files",
    )
    parser.add_argument(
        "--document-id",
        default="shadowdark-v4.8",
        help="Document ID to stamp into fixture fields.document",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser() if args.repo_root else Path(__file__).resolve().parents[2]
    if not repo_root.is_absolute():
        repo_root = (Path.cwd() / repo_root).resolve()

    pdf_dir = Path(args.pdf_dir).expanduser()
    if not pdf_dir.is_absolute():
        pdf_dir = repo_root / pdf_dir

    out_dir = Path(args.out_dir).expanduser()
    if not out_dir.is_absolute():
        out_dir = repo_root / out_dir

    pdf_paths = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_paths:
        eprint(f"ERROR: no PDFs found in {pdf_dir}")
        return 2

    text = load_pdf_text(pdf_paths)
    eprint(f"[bootstrap_shadowdark] loaded_pdfs={len(pdf_paths)} text_chars={len(text)}")

    known_classes = ["Fighter", "Priest", "Thief", "Wizard"]
    known_spells = [
        "Light",
        "Sleep",
        "Magic Missile",
        "Shield",
        "Charm Person",
        "Detect Magic",
        "Knock",
        "Invisibility",
    ]
    known_items = [
        "Torch",
        "Lantern",
        "Oil Flask",
        "Rope",
        "Rations",
        "Iron Spikes",
        "Crowbar",
        "Grappling Hook",
    ]
    known_creatures = [
        "Goblin",
        "Orc",
        "Skeleton",
        "Giant Rat",
        "Wolf",
        "Zombie",
        "Bandit",
        "Cultist",
    ]
    known_rules = [
        "Advantage and Disadvantage",
        "Torchlight and Darkness",
        "Real-Time Turns",
        "Death Timer",
        "Morale Checks",
        "Reaction Rolls",
        "Inventory Slots",
    ]

    classes = extract_known_terms(text, known_classes) or known_classes
    spells = extract_known_terms(text, known_spells) or known_spells
    items = extract_known_terms(text, known_items) or known_items
    creatures = extract_known_terms(text, known_creatures) or known_creatures
    rules = extract_known_terms(text, known_rules) or known_rules

    datasets: list[tuple[str, str, list[str]]] = [
        ("CharacterClass.json", "reference.characterclass", classes),
        ("Spell.json", "reference.spell", spells),
        ("Item.json", "reference.item", items),
        ("Creature.json", "reference.creature", creatures),
        ("Rule.json", "reference.rule", rules),
    ]

    for filename, model, names in datasets:
        records = to_fixture_records(model, names, args.document_id)
        write_json(out_dir / filename, records)
        eprint(f"[bootstrap_shadowdark] wrote {filename} records={len(records)}")

    # Required join files for current config/attach_fact path; empty is valid.
    for filename in [
        "CreatureAction.json",
        "CreatureActionAttack.json",
        "CreatureTrait.json",
        "SpellCastingOption.json",
    ]:
        write_json(out_dir / filename, [])
        eprint(f"[bootstrap_shadowdark] wrote {filename} records=0")

    eprint(f"[bootstrap_shadowdark] output_dir={out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
