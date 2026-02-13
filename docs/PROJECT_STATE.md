# Project State

Last updated: 2026-02-13

## Mission
Operate a reliable daily RPG Shorts production system with human-in-the-loop approval:
- generate daily atom from weighted topic spine
- produce polished Hook/Body/CTA script
- render daily vertical video
- request Discord approval before publish
- preserve monthly bundle/manifest continuity

## Current Status (Production-Ready Foundation)
- Daily weighted generation pipeline is stable on Umbrel
- Script quality controls are active:
  - anti-generic gates
  - encounter hook/CTA hard-guards
  - low-DC humor lane for low-stakes picks
  - best-effort PDF flavor enrichment + diagnostics
- Render pipeline is stable with dynamic timing:
  - word-count-based Hook/Body/CTA pacing
  - category-aware CTA timing profile
- Discord operations are active:
  - RED/GREEN health notifications
  - daily approval request post with expected command formats
  - approve/reject parsing from channel (no thread required)
  - stage notifications: approval accepted, publish started, publish complete/failed
- Cron automation is managed via install/uninstall scripts and runs on Mountain local-time defaults (8:00 PM)
- Monthly manifest + zine pack release tooling is in place

## Automation Snapshot
- Managed cron block marker: `# BEGIN BIZZAL_AUTOMATION` … `# END BIZZAL_AUTOMATION`
- Daily run: `bin/core/run_daily_diag_cron.sh` (8:00 PM MT)
- Approval poller: `bin/core/discord_publish_gate.py check --publish` (every 5 minutes)
- Weekly log prune: `bin/core/prune_daily_diag_logs.sh --keep-days 30`
- Monthly bundle: `bin/core/monthly_release_cron.sh "$(date -d 'last month' +%Y-%m)"`

## Key Control Flags
- `BIZZAL_ENABLE_AI=1`
- `BIZZAL_ENABLE_AI_SCRIPT=1`
- `BIZZAL_ENABLE_PDF_FLAVOR=1`
- `BIZZAL_REQUIRE_PDF_FLAVOR=0` (best-effort default)
- `BIZZAL_ENABLE_LOW_DC_HUMOR=1`
- `BIZZAL_REQUIRE_DISCORD_APPROVAL=1`

## Known Constraints / Open Items
- Publish command is environment-dependent; set `BIZZAL_PUBLISH_CMD` if no native uploader exists
- Discord approval path requires valid bot token + channel ID + approver user IDs
- Keep cron free of duplicate legacy lines outside managed block

## Next Session Priorities
1. Add Discord config doctor/check script (single-command env + API sanity check)
2. Finalize publish command adapter (real platform command + failure policy)
3. Optional: tighten low-stakes pick rules by category while preserving humor lane

## Resume Command (Umbrel)
```bash
cd /home/umbrel/Bizzal_Games_Pub && git pull --ff-only && bin/core/run_daily_diag.sh
```
