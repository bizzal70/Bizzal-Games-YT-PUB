#!/usr/bin/env python3
"""
Verifies the DB-backed config (system_config.py) is equivalent to the legacy
YAML files before they get deleted. Run after migrate_config_to_db.py:

    BIZZAL_DB_URL=postgresql://... python3 bin/core/verify_config_migration.py

Exits non-zero with a diff summary if anything doesn't match.
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import system_config  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent.parent

PAIRS = [
    ("dnd5e", "config/topic_spine.yaml", system_config.load_topic_spine),
    ("shadowdark", "config/topic_spine_shadowdark.yaml", system_config.load_topic_spine),
    ("dnd5e", "config/style_rules.yaml", system_config.load_style_rules),
    ("shadowdark", "config/style_rules_shadowdark.yaml", system_config.load_style_rules),
    ("dnd5e", "config/reference_sources.yaml", system_config.load_reference_sources),
    ("shadowdark", "config/reference_sources_shadowdark.yaml", system_config.load_reference_sources),
]


def normalize(d):
    """Sort lists/sets for order-insensitive comparison; YAML list order
    isn't semantically meaningful for most of these fields (weighted dicts,
    voice/angle pools)."""
    if isinstance(d, dict):
        return {k: normalize(v) for k, v in sorted(d.items())}
    if isinstance(d, list):
        try:
            return sorted(normalize(x) for x in d)
        except TypeError:
            return [normalize(x) for x in d]
    return d


def main():
    failures = []
    for system_id, yaml_rel_path, loader in PAIRS:
        yaml_path = REPO_ROOT / yaml_rel_path
        if not yaml_path.exists():
            print(f"SKIP {yaml_rel_path} (already removed)")
            continue
        expected = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        actual = loader(system_id)

        if normalize(expected) != normalize(actual):
            failures.append((system_id, yaml_rel_path))
            print(f"MISMATCH: {system_id} vs {yaml_rel_path}")
            print(f"  expected keys: {sorted(expected.keys())}")
            print(f"  actual keys:   {sorted(actual.keys())}")
            for k in expected:
                if normalize(expected.get(k)) != normalize(actual.get(k)):
                    print(f"  field '{k}' differs:")
                    print(f"    expected: {expected.get(k)!r}")
                    print(f"    actual:   {actual.get(k)!r}")
        else:
            print(f"OK: {system_id} matches {yaml_rel_path}")

    if failures:
        print(f"\n{len(failures)} mismatch(es) found. Do not delete the YAML files yet.")
        sys.exit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
