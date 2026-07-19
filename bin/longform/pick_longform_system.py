#!/usr/bin/env python3
"""
pick_longform_system.py -- print the system id whose turn it is for today's
long-form, rotating through every ACTIVE system in the rpg_systems DB.

This replaces the hardcoded Mon=dnd5e/Wed=shadowdark/Fri=dcc rotation so a new
system (added to the DB + given SRD files) is included automatically. Rotation
is by ordinal date, so successive long-form days cycle through all systems and
the choice is stable for a given date (both DST cron triggers agree).

Falls back to the historical three if the DB is unreachable.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../core"))

_FALLBACK = ["dnd5e", "shadowdark", "dcc"]


def active_systems():
    try:
        import system_config
        ids = system_config.list_active_system_ids()
        return ids or _FALLBACK
    except Exception:
        return _FALLBACK


def main():
    ids = active_systems()
    idx = date.today().toordinal() % len(ids)
    print(ids[idx])


if __name__ == "__main__":
    main()
