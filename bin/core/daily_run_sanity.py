#!/usr/bin/env python3
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def file_ok(path: Path) -> tuple[bool, int]:
    if not path.is_file():
        return False, 0
    try:
        size = path.stat().st_size
    except Exception:
        return False, 0
    return size > 0, size


def resolve_repo_path(repo_root: Path, raw: str, default_rel: str) -> Path:
    val = (raw or "").strip() or default_rel
    p = Path(val).expanduser()
    if not p.is_absolute():
        p = repo_root / p
    return p


def has_marker(log_text: str, marker: str) -> bool:
    return marker in log_text


def parse_approval_status(repo_root: Path, day: str) -> tuple[str, str]:
    state_path = resolve_repo_path(
        repo_root,
        os.getenv("BIZZAL_DISCORD_APPROVAL_STATE", ""),
        "data/archive/approvals/discord_publish_gate.json",
    )
    if not state_path.is_file():
        return "missing_state", ""
    try:
        obj = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return "invalid_state", ""
    approvals = obj.get("approvals") if isinstance(obj, dict) else None
    if not isinstance(approvals, dict):
        return "missing_approvals", ""
    entry = approvals.get(day)
    if not isinstance(entry, dict):
        return "missing_day", ""
    return str(entry.get("status") or "unknown"), str(entry.get("content_id") or "")


def build_report(repo_root: Path, day: str, log_path: Path) -> dict:
    log_text = read_text(log_path)
    artifacts_dir = resolve_repo_path(
        repo_root,
        os.getenv("BIZZAL_RENDERS_BY_DAY_DIR", ""),
        "data/renders/by_day",
    )

    mp4 = artifacts_dir / f"{day}.mp4"
    voice = artifacts_dir / f"{day}.voice.wav"
    music = artifacts_dir / f"{day}.music.wav"
    bg = artifacts_dir / f"{day}.bg.png"

    checks = []

    done_ok = has_marker(log_text, "[run_daily] DONE")
    checks.append(("pipeline_done", done_ok, "missing [run_daily] DONE marker"))

    tts_marker_ok = "[tts] wrote" in log_text
    checks.append(("tts_marker", tts_marker_ok, "missing [tts] wrote marker"))

    bg_marker_ok = "[bgimg] wrote" in log_text
    checks.append(("bgimg_marker", bg_marker_ok, "missing [bgimg] wrote marker"))

    music_marker_ok = "[music] wrote" in log_text
    checks.append(("music_marker", music_marker_ok, "missing [music] wrote marker"))

    mp4_ok, mp4_size = file_ok(mp4)
    checks.append(("artifact_mp4", mp4_ok, f"missing/empty {mp4}"))

    voice_ok, voice_size = file_ok(voice)
    checks.append(("artifact_voice", voice_ok, f"missing/empty {voice}"))

    music_ok, music_size = file_ok(music)
    checks.append(("artifact_music", music_ok, f"missing/empty {music}"))

    bg_ok, bg_size = file_ok(bg)
    checks.append(("artifact_bg", bg_ok, f"missing/empty {bg}"))

    approval_status, content_id = parse_approval_status(repo_root, day)
    approval_ok = approval_status in {"pending", "approved", "published", "approved_publish_failed", "rejected"}
    checks.append(("approval_state", approval_ok, f"approval state missing for day={day}"))

    failures = [msg for _, ok, msg in checks if not ok]
    overall = "GREEN" if not failures else "RED"

    return {
        "day": day,
        "overall": overall,
        "log_path": str(log_path),
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
        "failures": failures,
        "artifacts": {
            "mp4": {"path": str(mp4), "ok": mp4_ok, "size": mp4_size},
            "voice": {"path": str(voice), "ok": voice_ok, "size": voice_size},
            "music": {"path": str(music), "ok": music_ok, "size": music_size},
            "bg": {"path": str(bg), "ok": bg_ok, "size": bg_size},
        },
        "approval": {
            "status": approval_status,
            "content_id": content_id,
        },
        "utc": utc_now(),
    }


def print_line_report(report: dict):
    checks = report.get("checks") or []
    failed_names = [c.get("name") for c in checks if not c.get("ok")]
    failed_txt = ",".join(failed_names) if failed_names else "none"
    approval = report.get("approval") or {}
    print(
        "DAILY_SANITY "
        f"{report.get('overall','RED')} "
        f"day={report.get('day','')} "
        f"failed={failed_txt} "
        f"approval={approval.get('status','unknown')} "
        f"log={report.get('log_path','')}"
    )


def post_discord(webhook_url: str, report: dict):
    webhook_url = (webhook_url or "").strip().replace("https://discordapp.com/", "https://discord.com/")
    if not webhook_url:
        raise RuntimeError("missing webhook url")

    overall = (report.get("overall") or "RED").upper()
    ok = overall == "GREEN"
    icon = "✅" if ok else "❌"
    color = 0x2ECC71 if ok else 0xE74C3C
    day = report.get("day") or ""
    approval = report.get("approval") or {}
    artifacts = report.get("artifacts") or {}
    failures = report.get("failures") or []

    fail_block = "none"
    if failures:
        fail_block = "\n".join(f"- {f}" for f in failures[:8])

    fields = [
        {"name": "Day", "value": str(day), "inline": True},
        {"name": "Overall", "value": overall, "inline": True},
        {"name": "Approval", "value": str(approval.get("status") or "unknown"), "inline": True},
        {"name": "MP4", "value": f"ok={artifacts.get('mp4',{}).get('ok')} size={artifacts.get('mp4',{}).get('size',0)}", "inline": True},
        {"name": "Voice", "value": f"ok={artifacts.get('voice',{}).get('ok')} size={artifacts.get('voice',{}).get('size',0)}", "inline": True},
        {"name": "Music", "value": f"ok={artifacts.get('music',{}).get('ok')} size={artifacts.get('music',{}).get('size',0)}", "inline": True},
        {"name": "BG", "value": f"ok={artifacts.get('bg',{}).get('ok')} size={artifacts.get('bg',{}).get('size',0)}", "inline": True},
        {"name": "Failed Checks", "value": f"```\n{fail_block}\n```", "inline": False},
    ]

    payload = {
        "username": "Bizzal Sanity Bot",
        "embeds": [
            {
                "title": f"{icon} Daily Run Sanity",
                "description": "All green" if ok else "Failed at one or more stages",
                "color": color,
                "fields": fields,
                "footer": {"text": f"UTC {report.get('utc','')}"},
            }
        ],
    }

    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "BizzalSanityBot/1.0",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            _ = resp.read()
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"discord webhook rejected: http={exc.code} body={body or '(empty)'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-run daily sanity check with optional Discord summary")
    parser.add_argument("--day", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--log", default="")
    parser.add_argument("--notify-discord", action="store_true")
    parser.add_argument("--webhook-url", default=os.getenv("BIZZAL_DISCORD_WEBHOOK_URL", ""))
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when sanity is RED")
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    day = args.day.strip()
    log_path = Path(args.log).expanduser() if args.log.strip() else Path(f"/tmp/bizzal_daily_{day}.log")
    if not log_path.is_absolute():
        log_path = repo_root / log_path

    report = build_report(repo_root, day, log_path)
    print_line_report(report)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    if args.notify_discord:
        try:
            post_discord(args.webhook_url, report)
            print("[daily_run_sanity] discord_summary=sent")
        except Exception as exc:
            print(f"[daily_run_sanity] discord_summary=failed err={exc}", file=sys.stderr)
            if args.strict:
                return 3

    if args.strict and (report.get("overall") or "RED") != "GREEN":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
