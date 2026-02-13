#!/usr/bin/env python3
import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
from datetime import datetime, timezone
from urllib import error, parse, request


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
            return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def save_json(path: str, obj: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def atom_for_day(repo_root: str, day: str) -> tuple[str, dict]:
    path = os.path.join(repo_root, "data", "atoms", "validated", f"{day}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"validated atom missing: {path}")
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    return path, obj


def short(text: str, n: int) -> str:
    t = " ".join((text or "").split())
    if len(t) <= n:
        return t
    cut = t[: n - 1]
    idx = cut.rfind(" ")
    if idx > 0:
        cut = cut[:idx]
    return cut + "…"


def webhook_post_json(url: str, payload: dict, wait: bool = False) -> dict:
    if wait:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}wait=true"
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "BizzalPublishGate/1.0"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        raise RuntimeError(f"discord webhook rejected: http={exc.code} body={body or '(empty)'}")
    if not raw.strip():
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def discord_get_messages(bot_token: str, channel_id: str, limit: int = 50) -> list:
    qs = parse.urlencode({"limit": max(1, min(limit, 100))})
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages?{qs}"
    req = request.Request(
        url,
        headers={
            "Authorization": f"Bot {bot_token}",
            "User-Agent": "BizzalPublishGate/1.0",
        },
        method="GET",
    )
    with request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    obj = json.loads(raw)
    return obj if isinstance(obj, list) else []


def parse_approval_command(content: str) -> tuple[str, str] | None:
    txt = (content or "").strip().lower()
    parts = txt.split()
    if len(parts) < 2:
        return None
    cmd = parts[0]
    arg = parts[1]
    if cmd in {"approve", "reject"}:
        return cmd, arg
    return None


def looks_like_placeholder_webhook(url: str) -> bool:
    u = (url or "").strip()
    if not u:
        return True
    if "..." in u or "YOUR_" in u.upper() or "REPLACE" in u.upper():
        return True
    if "discord.com/api/webhooks/" not in u:
        return True
    return False


def run_publish_command(repo_root: str, day: str) -> tuple[int, str]:
    cmd_env = os.getenv("BIZZAL_PUBLISH_CMD", "").strip()
    if cmd_env:
        cmd = shlex.split(cmd_env)
    elif os.path.exists(os.path.join(repo_root, "bin", "upload", "upload_youtube.py")):
        cmd = [os.path.join(repo_root, "bin", "upload", "upload_youtube.py")]
    else:
        return 10, "no publish command available"

    proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return proc.returncode, out


def request_mode(repo_root: str, day: str, state_path: str, webhook_url: str, force: bool) -> int:
    if not webhook_url:
        print("ERROR: missing BIZZAL_DISCORD_WEBHOOK_URL", file=sys.stderr)
        return 2
    if looks_like_placeholder_webhook(webhook_url):
        print("ERROR: BIZZAL_DISCORD_WEBHOOK_URL looks invalid/placeholder; set a real Discord webhook URL", file=sys.stderr)
        return 2

    atom_path, atom = atom_for_day(repo_root, day)
    content = atom.get("content") or {}
    script = atom.get("script") or {}
    content_id = str(content.get("content_id") or "")
    if not content_id:
        print(f"ERROR: content_id missing in {atom_path}", file=sys.stderr)
        return 3

    state = load_json(state_path)
    approvals = state.setdefault("approvals", {})
    existing = approvals.get(day)
    if isinstance(existing, dict) and existing.get("content_id") == content_id and existing.get("status") in {"pending", "approved", "published"} and not force:
        print(f"[discord_publish_gate] request exists day={day} status={existing.get('status')} content_id={content_id}")
        return 0

    category = atom.get("category") or ""
    angle = atom.get("angle") or ""
    hook = short(script.get("hook") or "", 220)
    body = short(script.get("body") or "", 340)
    cta = short(script.get("cta") or "", 180)

    payload = {
        "username": "Bizzal Publish Gate",
        "content": (
            f"Daily draft ready for approval on `{day}`\n"
            f"Reply with: `approve {day}` or `approve {content_id}`\n"
            f"Reject with: `reject {day}`"
        ),
        "embeds": [
            {
                "title": "🎬 Publish Approval Request",
                "description": f"`{category}` • `{angle}` • `{content_id}`",
                "color": 0x5865F2,
                "fields": [
                    {"name": "Hook", "value": hook or "(empty)", "inline": False},
                    {"name": "Body", "value": body or "(empty)", "inline": False},
                    {"name": "CTA", "value": cta or "(empty)", "inline": False},
                ],
                "footer": {"text": f"host={socket.gethostname()} utc={now_utc()}"},
            }
        ],
    }

    try:
        response = webhook_post_json(webhook_url, payload, wait=True)
    except Exception as exc:
        print(f"ERROR: failed to send approval request webhook: {exc}", file=sys.stderr)
        return 4
    msg_id = str(response.get("id") or "")

    approvals[day] = {
        "day": day,
        "content_id": content_id,
        "category": category,
        "angle": angle,
        "status": "pending",
        "requested_utc": now_utc(),
        "request_message_id": msg_id,
    }
    save_json(state_path, state)
    print(f"[discord_publish_gate] requested day={day} content_id={content_id} message_id={msg_id or 'na'}")
    return 0


def check_mode(repo_root: str, state_path: str, bot_token: str, channel_id: str, approve_users: set[str], webhook_url: str, publish: bool) -> int:
    state = load_json(state_path)
    approvals = state.get("approvals") or {}
    pending_days = [d for d, v in approvals.items() if isinstance(v, dict) and v.get("status") == "pending"]
    if not pending_days:
        print("[discord_publish_gate] no pending approvals")
        return 0

    if not bot_token or not channel_id:
        print("ERROR: missing bot token/channel id for approval check", file=sys.stderr)
        return 2

    try:
        messages = discord_get_messages(bot_token, channel_id, limit=80)
    except Exception as exc:
        print(f"ERROR: failed to read discord channel messages: {exc}", file=sys.stderr)
        return 3

    changed = False
    for msg in messages:
        author = msg.get("author") or {}
        uid = str(author.get("id") or "")
        if approve_users and uid not in approve_users:
            continue
        parsed = parse_approval_command(msg.get("content") or "")
        if not parsed:
            continue
        cmd, arg = parsed

        for day in list(pending_days):
            entry = approvals.get(day) or {}
            if entry.get("status") != "pending":
                continue
            content_id = str(entry.get("content_id") or "")
            if arg not in {day.lower(), content_id.lower()}:
                continue

            if cmd == "reject":
                entry["status"] = "rejected"
                entry["decision_utc"] = now_utc()
                entry["decision_by"] = uid
                approvals[day] = entry
                changed = True
                print(f"[discord_publish_gate] rejected day={day} by={uid}")
                continue

            entry["status"] = "approved"
            entry["decision_utc"] = now_utc()
            entry["decision_by"] = uid

            if publish:
                rc, output = run_publish_command(repo_root, day)
                entry["publish_rc"] = rc
                entry["publish_output"] = short(output, 800)
                if rc == 0:
                    entry["status"] = "published"
                    print(f"[discord_publish_gate] approved+pushed day={day} by={uid}")
                else:
                    entry["status"] = "approved_publish_failed"
                    print(f"[discord_publish_gate] approved but publish failed day={day} rc={rc}")
            else:
                print(f"[discord_publish_gate] approved day={day} by={uid}")

            approvals[day] = entry
            changed = True

            if webhook_url:
                try:
                    webhook_post_json(
                        webhook_url,
                        {
                            "username": "Bizzal Publish Gate",
                            "content": f"Decision recorded for `{day}`: `{approvals[day].get('status')}`",
                        },
                        wait=False,
                    )
                except Exception:
                    pass

    if changed:
        state["approvals"] = approvals
        save_json(state_path, state)
    return 0


def main() -> int:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

    parser = argparse.ArgumentParser(description="Discord approval gate for daily publish.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    req = sub.add_parser("request", help="Send approval request for a validated day")
    req.add_argument("--day", default=datetime.now().strftime("%Y-%m-%d"))
    req.add_argument("--force", action="store_true")

    chk = sub.add_parser("check", help="Check Discord replies and apply approvals")
    chk.add_argument("--publish", action="store_true", help="Run publish command when approved")

    args = parser.parse_args()

    state_file = os.getenv("BIZZAL_DISCORD_APPROVAL_STATE", "data/archive/approvals/discord_publish_gate.json")
    if not os.path.isabs(state_file):
        state_file = os.path.join(repo_root, state_file)

    webhook_url = (os.getenv("BIZZAL_DISCORD_WEBHOOK_URL") or "").strip()

    if args.cmd == "request":
        return request_mode(repo_root, args.day.strip(), state_file, webhook_url, args.force)

    bot_token = (os.getenv("BIZZAL_DISCORD_BOT_TOKEN") or "").strip()
    channel_id = (os.getenv("BIZZAL_DISCORD_CHANNEL_ID") or "").strip()
    approved = (os.getenv("BIZZAL_DISCORD_APPROVER_USER_IDS") or "").strip()
    approve_users = {x.strip() for x in approved.split(",") if x.strip()}
    return check_mode(repo_root, state_file, bot_token, channel_id, approve_users, webhook_url, args.publish)


if __name__ == "__main__":
    raise SystemExit(main())
