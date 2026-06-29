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


def parse_utc_timestamp(value: str):
    txt = (value or "").strip()
    if not txt:
        return None
    try:
        if txt.endswith("Z"):
            txt = txt[:-1] + "+00:00"
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


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


def normalize_webhook_url(url: str) -> str:
    u = (url or "").strip()
    if len(u) >= 2 and ((u[0] == u[-1]) and u[0] in {"'", '"'}):
        u = u[1:-1].strip()
    u = u.replace("https://discordapp.com/", "https://discord.com/")
    u = u.replace("http://discordapp.com/", "https://discord.com/")
    return u


def normalize_discord_id(value: str) -> str:
    txt = (value or "").strip()
    if len(txt) >= 2 and ((txt[0] == txt[-1]) and txt[0] in {"'", '"'}):
        txt = txt[1:-1].strip()
    txt = txt.replace("<", "").replace(">", "").replace("#", "").replace("@", "").replace("&", "")
    return "".join(ch for ch in txt if ch.isdigit())


def looks_like_placeholder_webhook(url: str) -> bool:
    u = normalize_webhook_url(url)
    if not u or "..." in u or "YOUR_" in u.upper() or "REPLACE" in u.upper():
        return True
    try:
        parsed = parse.urlparse(u)
    except Exception:
        return True
    if parsed.scheme != "https":
        return True
    if not parsed.netloc.endswith("discord.com"):
        return True
    return "/api/webhooks/" not in (parsed.path or "")


def webhook_post_json(url: str, payload: dict, wait: bool = False) -> dict:
    if wait:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}wait=true"
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "BizzalMonthlyGate/1.0"},
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


def discord_get_messages(bot_token: str, channel_id: str, limit: int = 80) -> list:
    qs = parse.urlencode({"limit": max(1, min(limit, 100))})
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages?{qs}"
    req = request.Request(
        url,
        headers={
            "Authorization": f"Bot {bot_token}",
            "User-Agent": "BizzalMonthlyGate/1.0",
        },
        method="GET",
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
        raise RuntimeError(f"discord get messages rejected: http={exc.code} body={body or '(empty)'}")
    obj = json.loads(raw)
    return obj if isinstance(obj, list) else []


def parse_approval_command(content: str):
    txt = (content or "").strip().lower()
    parts = txt.split()
    if not parts:
        return None
    cmd = {
        "approve": "approve",
        "approved": "approve",
        "reject": "reject",
        "rejected": "reject",
    }.get(parts[0])
    if not cmd:
        return None
    arg = parts[1] if len(parts) >= 2 else ""
    return cmd, arg


def short(text: str, n: int) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def chain_tag() -> str:
    explicit = (os.getenv("BIZZAL_DISCORD_CHAIN_TAG") or os.getenv("BIZZAL_CHAIN_TAG") or "").strip()
    if explicit:
        return explicit

    label = (os.getenv("BIZZAL_CHAIN_LABEL") or "").strip().lower()
    if label in {"shadowdark", "sd"}:
        return "Shadowdark"
    if label in {"dnd", "d&d", "srd", "5e"}:
        return "D&D"
    return "D&D"


def gate_username() -> str:
    return f"Bizzal Monthly Gate • {chain_tag()}"


def run_monthly_publish_command(repo_root: str, month: str):
    cmd_env = os.getenv("BIZZAL_MONTHLY_PUBLISH_CMD", "").strip()
    if cmd_env:
        try:
            cmd = shlex.split(cmd_env)
        except ValueError as exc:
            return 13, f"invalid BIZZAL_MONTHLY_PUBLISH_CMD quoting: {exc}"
    else:
        cmd = [os.path.join(repo_root, "bin", "upload", "upload_youtube_monthly.py"), "--month", month]

    try:
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, env=os.environ.copy())
    except FileNotFoundError as exc:
        return 11, f"publish command executable not found: {exc}"
    except Exception as exc:
        return 12, f"publish command failed to launch: {exc}"

    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return proc.returncode, out


def extract_youtube_url(text: str) -> str:
    for line in (text or "").splitlines():
        txt = line.strip()
        if txt.startswith("https://www.youtube.com/watch?v="):
            return txt
    return ""


def monthly_longform_exists(repo_root: str, month: str) -> bool:
    monthly_root = (os.getenv("BIZZAL_MONTHLY_ROOT") or "data/archive/monthly").strip()
    if os.path.isabs(monthly_root):
        path = os.path.join(monthly_root, month, f"monthly_longform_{month}.mp4")
    else:
        path = os.path.join(repo_root, monthly_root, month, f"monthly_longform_{month}.mp4")
    return os.path.isfile(path)


def request_mode(repo_root: str, month: str, state_path: str, webhook_url: str, force: bool) -> int:
    if len(month) != 7 or month[4] != "-":
        print("ERROR: --month must be YYYY-MM", file=sys.stderr)
        return 2
    if not monthly_longform_exists(repo_root, month):
        print(f"ERROR: monthly longform video missing for month={month}", file=sys.stderr)
        return 3

    webhook_url = normalize_webhook_url(webhook_url)
    if not webhook_url:
        print("ERROR: missing BIZZAL_DISCORD_WEBHOOK_URL", file=sys.stderr)
        return 2
    if looks_like_placeholder_webhook(webhook_url):
        print("ERROR: BIZZAL_DISCORD_WEBHOOK_URL looks invalid/placeholder", file=sys.stderr)
        return 2

    state = load_json(state_path)
    approvals = state.setdefault("approvals", {})
    existing = approvals.get(month)
    if isinstance(existing, dict) and existing.get("status") in {"pending", "approved", "published"} and not force:
        print(f"[monthly_publish_gate] request exists month={month} status={existing.get('status')}")
        return 0

    payload = {
        "username": gate_username(),
        "content": (
            f"Monthly longform ready for approval: `{month}`\n"
            f"Reply with: `approve {month}` or `reject {month}`"
        ),
        "embeds": [
            {
                "title": "🎬 Monthly Longform Approval Request",
                "description": f"Month `{month}` ready for private YouTube upload.",
                "color": 0x5865F2,
                "footer": {"text": f"host={socket.gethostname()} utc={now_utc()}"},
            }
        ],
    }

    try:
        response = webhook_post_json(webhook_url, payload, wait=True)
    except Exception as exc:
        print(f"ERROR: failed to send monthly approval webhook: {exc}", file=sys.stderr)
        return 4

    msg_id = str(response.get("id") or "")
    approvals[month] = {
        "month": month,
        "status": "pending",
        "requested_utc": now_utc(),
        "request_message_id": msg_id,
    }
    save_json(state_path, state)
    print(f"[monthly_publish_gate] requested month={month} message_id={msg_id or 'na'}")
    return 0


def check_mode(repo_root: str, state_path: str, bot_token: str, channel_id: str, approve_users: set[str], webhook_url: str, publish: bool) -> int:
    state = load_json(state_path)
    approvals = state.get("approvals") or {}
    pending_months = [m for m, v in approvals.items() if isinstance(v, dict) and v.get("status") == "pending"]
    if not pending_months:
        print("[monthly_publish_gate] no pending approvals")
        return 0

    if not bot_token or not channel_id:
        print("ERROR: missing bot token/channel id for monthly approval check", file=sys.stderr)
        return 2

    try:
        messages = discord_get_messages(bot_token, channel_id, limit=80)
    except Exception as exc:
        print(f"ERROR: failed to read discord channel messages: {exc}", file=sys.stderr)
        return 3

    changed = False
    for msg in messages:
        uid = str((msg.get("author") or {}).get("id") or "")
        if approve_users and uid not in approve_users:
            continue
        parsed = parse_approval_command(msg.get("content") or "")
        if not parsed:
            continue
        cmd, arg = parsed
        arg = (arg or "").strip().lower()

        target_months = list(pending_months)
        if not arg:
            if len(pending_months) == 1:
                target_months = [pending_months[0]]
            else:
                continue

        for month in target_months:
            entry = approvals.get(month) or {}
            if entry.get("status") != "pending":
                continue
            if arg and arg != month.lower():
                continue

            request_ts = parse_utc_timestamp(str(entry.get("requested_utc") or ""))
            msg_ts = parse_utc_timestamp(str(msg.get("timestamp") or ""))
            if request_ts and msg_ts and msg_ts < request_ts:
                continue

            if cmd == "reject":
                entry["status"] = "rejected"
                entry["decision_utc"] = now_utc()
                entry["decision_by"] = uid
                approvals[month] = entry
                changed = True
                print(f"[monthly_publish_gate] rejected month={month} by={uid}")
                if webhook_url:
                    try:
                        webhook_post_json(
                            webhook_url,
                            {
                                "username": gate_username(),
                                "content": f"🛑 Monthly rejected `{month}` by <@{uid}>.",
                            },
                            wait=False,
                        )
                    except Exception:
                        pass
                continue

            entry["status"] = "approved"
            entry["decision_utc"] = now_utc()
            entry["decision_by"] = uid

            if webhook_url:
                try:
                    webhook_post_json(
                        webhook_url,
                        {
                            "username": gate_username(),
                            "content": f"✅ Monthly approval accepted for `{month}` by <@{uid}>.",
                        },
                        wait=False,
                    )
                except Exception:
                    pass

            if publish:
                approvals[month] = entry
                state["approvals"] = approvals
                save_json(state_path, state)

                if webhook_url:
                    try:
                        webhook_post_json(
                            webhook_url,
                            {
                                "username": gate_username(),
                                "content": f"🚀 Monthly publish started for `{month}`.",
                            },
                            wait=False,
                        )
                    except Exception:
                        pass

                rc, output = run_monthly_publish_command(repo_root, month)
                entry["publish_rc"] = rc
                entry["publish_output"] = short(output, 900)
                youtube_url = extract_youtube_url(output)
                if rc == 0:
                    entry["status"] = "published"
                    if youtube_url:
                        entry["youtube_url"] = youtube_url
                    print(f"[monthly_publish_gate] approved+published month={month} by={uid}")
                    if webhook_url:
                        try:
                            msg = f"🎉 Monthly publish complete for `{month}`."
                            if youtube_url:
                                msg += f"\n🔗 {youtube_url}"
                            webhook_post_json(
                                webhook_url,
                                {
                                    "username": gate_username(),
                                    "content": msg,
                                },
                                wait=False,
                            )
                        except Exception:
                            pass
                else:
                    entry["status"] = "approved_publish_failed"
                    print(f"[monthly_publish_gate] approved but publish failed month={month} rc={rc}")
                    if webhook_url:
                        try:
                            msg = f"❌ Monthly publish failed for `{month}`, rc={rc}. Check logs."
                            if youtube_url:
                                msg += f"\n🔗 Related video: {youtube_url}"
                            webhook_post_json(
                                webhook_url,
                                {
                                    "username": gate_username(),
                                    "content": msg,
                                },
                                wait=False,
                            )
                        except Exception:
                            pass
            else:
                print(f"[monthly_publish_gate] approved month={month} by={uid}")
                if webhook_url:
                    try:
                        webhook_post_json(
                            webhook_url,
                            {
                                "username": gate_username(),
                                "content": f"ℹ️ Monthly `{month}` approved and queued; publish runner not executed in this check.",
                            },
                            wait=False,
                        )
                    except Exception:
                        pass

            approvals[month] = entry
            changed = True

    if changed:
        state["approvals"] = approvals
        save_json(state_path, state)
    return 0


def main() -> int:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

    parser = argparse.ArgumentParser(description="Discord approval gate for monthly longform publish")
    sub = parser.add_subparsers(dest="cmd", required=True)

    req = sub.add_parser("request", help="Send monthly approval request")
    req.add_argument("--month", default=datetime.now().strftime("%Y-%m"))
    req.add_argument("--force", action="store_true")

    chk = sub.add_parser("check", help="Check Discord replies and apply monthly approvals")
    chk.add_argument("--publish", action="store_true", help="Run monthly publish command when approved")

    args = parser.parse_args()

    state_file = os.getenv("BIZZAL_DISCORD_MONTHLY_APPROVAL_STATE", "data/archive/approvals/discord_monthly_publish_gate.json")
    if not os.path.isabs(state_file):
        state_file = os.path.join(repo_root, state_file)

    webhook_url = normalize_webhook_url((os.getenv("BIZZAL_DISCORD_WEBHOOK_URL") or "").strip())
    if args.cmd == "request":
        return request_mode(repo_root, args.month.strip(), state_file, webhook_url, args.force)

    bot_token = (os.getenv("BIZZAL_DISCORD_BOT_TOKEN") or "").strip()
    channel_id = normalize_discord_id((os.getenv("BIZZAL_DISCORD_CHANNEL_ID") or "").strip())
    approved = (os.getenv("BIZZAL_DISCORD_APPROVER_USER_IDS") or "").strip()
    approve_users = {normalize_discord_id(x.strip()) for x in approved.split(",") if normalize_discord_id(x.strip())}
    return check_mode(repo_root, state_file, bot_token, channel_id, approve_users, webhook_url, args.publish)


if __name__ == "__main__":
    raise SystemExit(main())
