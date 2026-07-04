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


def parse_utc_timestamp(value: str) -> datetime | None:
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


def validated_atom_dir(repo_root: str) -> str:
    raw = (os.getenv("BIZZAL_ATOM_VALIDATED_DIR") or "data/atoms/validated").strip()
    if os.path.isabs(raw):
        return raw
    return os.path.join(repo_root, raw)


def atom_for_day(repo_root: str, day: str) -> tuple[str, dict]:
    path = os.path.join(validated_atom_dir(repo_root), f"{day}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"validated atom missing: {path}")
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    return path, obj


def latest_validated_day(repo_root: str) -> str | None:
    validated_dir = validated_atom_dir(repo_root)
    if not os.path.isdir(validated_dir):
        return None
    days: list[str] = []
    for name in os.listdir(validated_dir):
        if not name.endswith(".json"):
            continue
        day = name[:-5]
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            continue
        days.append(day)
    if not days:
        return None
    return sorted(days)[-1]


def short(text: str, n: int) -> str:
    t = " ".join((text or "").split())
    if len(t) <= n:
        return t
    cut = t[: n - 1]
    idx = cut.rfind(" ")
    if idx > 0:
        cut = cut[:idx]
    return cut + "…"


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
    return f"Bizzal Publish Gate • {chain_tag()}"


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


def parse_approval_command(content: str) -> tuple[str, str] | None:
    txt = (content or "").strip().lower()
    parts = txt.split()
    if not parts:
        return None
    cmd = parts[0]
    cmd_alias = {
        "approve": "approve",
        "approved": "approve",
        "reject": "reject",
        "rejected": "reject",
    }.get(cmd)
    if not cmd_alias:
        return None
    arg = parts[1] if len(parts) >= 2 else ""
    if cmd_alias in {"approve", "reject"}:
        return cmd_alias, arg
    return None


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
    if not u:
        return True
    if "..." in u or "YOUR_" in u.upper() or "REPLACE" in u.upper():
        return True

    try:
        parsed = parse.urlparse(u)
    except Exception:
        return True

    if parsed.scheme != "https":
        return True
    if not parsed.netloc.endswith("discord.com"):
        return True
    if "/api/webhooks/" not in (parsed.path or ""):
        return True

    return False


def run_publish_command(repo_root: str, day: str) -> tuple[int, str]:
    cmd_env = os.getenv("BIZZAL_PUBLISH_CMD", "").strip()
    if cmd_env:
        try:
            cmd = shlex.split(cmd_env)
        except ValueError as exc:
            return 13, f"invalid BIZZAL_PUBLISH_CMD quoting: {exc}"
    elif os.path.exists(os.path.join(repo_root, "bin", "upload", "upload_youtube.py")):
        cmd = [sys.executable, os.path.join(repo_root, "bin", "upload", "upload_youtube.py")]
    else:
        return 10, "no publish command available"

    try:
        env = os.environ.copy()
        env["BIZZAL_DAY"] = day
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, env=env)
    except FileNotFoundError as exc:
        return 11, f"publish command executable not found: {exc}"
    except Exception as exc:
        return 12, f"publish command failed to launch: {exc}"

    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return proc.returncode, out


def publish_registry_path(repo_root: str) -> str:
    path = (os.getenv("BIZZAL_PUBLISH_REGISTRY") or "data/archive/publish/published_registry.json").strip()
    if os.path.isabs(path):
        return path
    return os.path.join(repo_root, path)


def load_publish_registry(repo_root: str) -> dict:
    path = publish_registry_path(repo_root)
    if not os.path.isfile(path):
        return {"items": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
            if isinstance(obj, dict) and isinstance(obj.get("items"), list):
                return obj
    except Exception:
        pass
    return {"items": []}


def find_published_item(registry: dict, day: str, content_id: str) -> dict | None:
    items = registry.get("items") or []
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        item_cid = str(item.get("content_id") or "")
        if content_id and item_cid == content_id:
            return item
        item_day = str(item.get("day") or "")
        if day and item_day == day and not content_id:
            return item
    return None


def published_item_url(item: dict) -> str:
    url = str(item.get("youtube_url") or "").strip()
    if url:
        return url
    vid = str(item.get("youtube_video_id") or "").strip()
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    return ""


def extract_youtube_url(text: str) -> str:
    for line in (text or "").splitlines():
        txt = line.strip()
        if txt.startswith("https://www.youtube.com/watch?v="):
            return txt
    return ""


def first_output_line(text: str) -> str:
    for line in (text or "").splitlines():
        txt = line.strip()
        if txt:
            return txt
    return ""


def publish_approved_entry(repo_root: str, day: str, entry: dict, webhook_url: str) -> dict:
    content_id = str(entry.get("content_id") or "")

    prior = find_published_item(load_publish_registry(repo_root), day, content_id)
    if prior:
        prior_url = published_item_url(prior)
        entry["status"] = "published"
        entry["publish_rc"] = 0
        entry["publish_output"] = f"already published; skipped upload url={prior_url or '(unknown)'}"
        if prior_url:
            entry["youtube_url"] = prior_url
        print(f"[discord_publish_gate] already published day={day}; skipped upload")
        if webhook_url:
            try:
                msg = f"ℹ️ Already published for `{day}` (`{content_id}`); skipping upload."
                if prior_url:
                    msg += f"\n🔗 {prior_url}"
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
        return entry

    if webhook_url:
        try:
            webhook_post_json(
                webhook_url,
                {
                    "username": gate_username(),
                    "content": f"🚀 Publish started for `{day}` (`{content_id}`).",
                },
                wait=False,
            )
        except Exception:
            pass

    rc, output = run_publish_command(repo_root, day)
    entry["publish_rc"] = rc
    entry["publish_output"] = short(output, 800)
    youtube_url = extract_youtube_url(output)
    if rc == 0:
        entry["status"] = "published"
        if youtube_url:
            entry["youtube_url"] = youtube_url
        print(f"[discord_publish_gate] approved+pushed day={day}")
        if webhook_url:
            try:
                msg = f"🎉 Publish complete for `{day}` (`{content_id}`)."
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
        return entry

    entry["status"] = "approved_publish_failed"
    print(f"[discord_publish_gate] approved but publish failed day={day} rc={rc}")
    if webhook_url:
        try:
            msg = f"❌ Publish failed for `{day}` (`{content_id}`), rc={rc}."
            failure_line = first_output_line(output)
            if failure_line:
                msg += f"\n{short(failure_line, 240)}"
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
    return entry


def request_mode(repo_root: str, day: str, state_path: str, webhook_url: str, force: bool) -> int:
    webhook_url = normalize_webhook_url(webhook_url)
    if not webhook_url:
        print("ERROR: missing BIZZAL_DISCORD_WEBHOOK_URL", file=sys.stderr)
        return 2
    if looks_like_placeholder_webhook(webhook_url):
        print("ERROR: BIZZAL_DISCORD_WEBHOOK_URL looks invalid/placeholder; set a real Discord webhook URL", file=sys.stderr)
        return 2

    requested_day = day
    try:
        atom_path, atom = atom_for_day(repo_root, day)
    except FileNotFoundError:
        fallback_day = latest_validated_day(repo_root)
        if not fallback_day:
            print(
                f"ERROR: validated atom missing for requested day {requested_day}, and no fallback atom exists",
                file=sys.stderr,
            )
            return 3
        day = fallback_day
        atom_path, atom = atom_for_day(repo_root, day)
        print(
            f"[discord_publish_gate] requested day={requested_day} missing; using latest validated day={day}",
            file=sys.stderr,
        )
    content = atom.get("content") or {}
    script = atom.get("script") or {}
    content_id = str(content.get("content_id") or "")
    category = atom.get("category") or ""
    angle = atom.get("angle") or ""
    if not content_id:
        print(f"ERROR: content_id missing in {atom_path}", file=sys.stderr)
        return 3

    state = load_json(state_path)
    approvals = state.setdefault("approvals", {})
    existing = approvals.get(day)
    if isinstance(existing, dict) and existing.get("content_id") == content_id and existing.get("status") in {"pending", "approved", "published"} and not force:
        print(f"[discord_publish_gate] request exists day={day} status={existing.get('status')} content_id={content_id}")
        return 0

    prior = find_published_item(load_publish_registry(repo_root), day, content_id)
    if prior and not force:
        prior_url = published_item_url(prior)
        approvals[day] = {
            "day": day,
            "content_id": content_id,
            "category": category,
            "angle": angle,
            "status": "published",
            "requested_utc": now_utc(),
            "decision_utc": str(prior.get("published_utc") or now_utc()),
            "decision_by": "system",
            "publish_rc": 0,
            "publish_output": f"already published; skipped approval request url={prior_url or '(unknown)'}",
            "youtube_url": prior_url,
        }
        save_json(state_path, state)
        print(f"[discord_publish_gate] already published day={day} content_id={content_id} url={prior_url or 'na'}")
        if webhook_url:
            try:
                msg = f"ℹ️ Already published for `{day}` (`{content_id}`); skipping approval request."
                if prior_url:
                    msg += f"\n🔗 {prior_url}"
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
        return 0
    hook = short(script.get("hook") or "", 220)
    body = short(script.get("body") or "", 340)
    cta = short(script.get("cta") or "", 180)

    payload = {
        "username": gate_username(),
        "content": (
            f"Daily draft ready for approval on `{day}`\n"
            f"Reply with: `approve {day}` or `approve {content_id}`\n"
            f"Reject with: `reject {day}`\n"
            "(Post directly in this channel; reply/thread not required.)"
        ),
        "embeds": [
            {
                "title": "🎬 Publish Approval Request",
                "description": f"`{category}` • `{angle}` • `{content_id}`",
                "color": 0x5865F2,
                "fields": [
                    {
                        "name": "Expected Responses",
                        "value": (
                            f"`approve {day}`\n"
                            f"`approve {content_id}`\n"
                            f"`reject {day}`\n"
                            f"`reject {content_id}`"
                        ),
                        "inline": False,
                    },
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
    upload_limit_exceeded = False
    for msg in messages:
        author = msg.get("author") or {}
        uid = str(author.get("id") or "")
        if approve_users and uid not in approve_users:
            continue
        parsed = parse_approval_command(msg.get("content") or "")
        if not parsed:
            continue
        cmd, arg = parsed
        arg = (arg or "").strip().lower()

        target_days = list(pending_days)
        if not arg:
            if len(pending_days) == 1:
                target_days = [pending_days[0]]
            else:
                continue

        for day in target_days:
            entry = approvals.get(day) or {}
            if entry.get("status") != "pending":
                continue
            content_id = str(entry.get("content_id") or "")
            if arg and arg not in {day.lower(), content_id.lower()}:
                continue

            request_ts = parse_utc_timestamp(str(entry.get("requested_utc") or ""))
            msg_ts = parse_utc_timestamp(str(msg.get("timestamp") or ""))
            if request_ts and msg_ts and msg_ts < request_ts:
                continue

            if cmd == "reject":
                entry["status"] = "rejected"
                entry["decision_utc"] = now_utc()
                entry["decision_by"] = uid
                approvals[day] = entry
                changed = True
                print(f"[discord_publish_gate] rejected day={day} by={uid}")
                if webhook_url:
                    try:
                        webhook_post_json(
                            webhook_url,
                            {
                                "username": gate_username(),
                                "content": f"🛑 Rejected `{day}` (`{content_id}`) by <@{uid}>.",
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
                            "content": f"✅ Approval accepted for `{day}` (`{content_id}`) by <@{uid}>.",
                        },
                        wait=False,
                    )
                except Exception:
                    pass

            if publish:
                approvals[day] = entry
                state["approvals"] = approvals
                save_json(state_path, state)

                entry = publish_approved_entry(repo_root, day, entry, webhook_url)
                if int(entry.get("publish_rc") or 0) == 14:
                    upload_limit_exceeded = True
            else:
                print(f"[discord_publish_gate] approved day={day} by={uid}")
                if webhook_url:
                    try:
                        webhook_post_json(
                            webhook_url,
                            {
                                "username": gate_username(),
                                "content": f"ℹ️ `{day}` approved and queued; publish runner not executed in this check.",
                            },
                            wait=False,
                        )
                    except Exception:
                        pass

            approvals[day] = entry
            changed = True

            if upload_limit_exceeded:
                print("[discord_publish_gate] upload limit exceeded; stopping further publish attempts in this run")
                break

        if upload_limit_exceeded:
            break

    if changed:
        state["approvals"] = approvals
        save_json(state_path, state)
    if upload_limit_exceeded:
        return 14
    return 0


def retry_mode(repo_root: str, day: str, state_path: str, webhook_url: str) -> int:
    state = load_json(state_path)
    approvals = state.get("approvals") or {}
    entry = approvals.get(day)
    if not isinstance(entry, dict):
        print(f"ERROR: no approval entry found for day={day}", file=sys.stderr)
        return 2

    status = str(entry.get("status") or "").strip().lower()
    if status == "published":
        print(f"[discord_publish_gate] already published day={day}")
        return 0
    if status not in {"approved", "approved_publish_failed"}:
        print(
            f"ERROR: cannot retry day={day} from status={status or '(missing)'}; needs approved or approved_publish_failed",
            file=sys.stderr,
        )
        return 3

    # The uploader enforces that the approval state is currently approved/published.
    # Move failed approvals back to approved before retrying the publish command.
    entry["status"] = "approved"
    approvals[day] = entry
    state["approvals"] = approvals
    save_json(state_path, state)

    entry = publish_approved_entry(repo_root, day, entry, webhook_url)
    approvals[day] = entry
    state["approvals"] = approvals
    save_json(state_path, state)
    return 0 if str(entry.get("status") or "") == "published" else int(entry.get("publish_rc") or 1)


def autopublish_mode(repo_root: str, day: str, state_path: str, webhook_url: str) -> int:
    """Publish a day's video directly, with no Discord approval round-trip.

    Used by the cloud (GitHub Actions) daily pipeline, where there is no human
    approval step. Reuses the same atom lookup as request_mode and the same
    publish + dedup-registry path as retry_mode (via publish_approved_entry),
    so double-publishes are still prevented by the publish registry. Discord
    messaging is suppressed by passing an empty webhook_url.
    """
    requested_day = day
    try:
        atom_path, atom = atom_for_day(repo_root, day)
    except FileNotFoundError:
        fallback_day = latest_validated_day(repo_root)
        if not fallback_day:
            print(
                f"ERROR: validated atom missing for requested day {requested_day}, and no fallback atom exists",
                file=sys.stderr,
            )
            return 3
        day = fallback_day
        atom_path, atom = atom_for_day(repo_root, day)
        print(
            f"[discord_publish_gate] autopublish: requested day={requested_day} missing; using latest validated day={day}",
            file=sys.stderr,
        )

    content = atom.get("content") or {}
    content_id = str(content.get("content_id") or "")
    if not content_id:
        print(f"ERROR: content_id missing in {atom_path}", file=sys.stderr)
        return 3

    state = load_json(state_path)
    approvals = state.setdefault("approvals", {})
    entry = {
        "day": day,
        "content_id": content_id,
        "category": atom.get("category") or "",
        "angle": atom.get("angle") or "",
        "status": "approved",
        "requested_utc": now_utc(),
        "decision_utc": now_utc(),
        "decision_by": "autopublish",
    }
    approvals[day] = entry
    save_json(state_path, state)

    entry = publish_approved_entry(repo_root, day, entry, webhook_url)
    approvals[day] = entry
    save_json(state_path, state)

    if str(entry.get("status") or "") == "published":
        print(f"[discord_publish_gate] autopublish complete day={day} content_id={content_id}")
        return 0
    print(f"[discord_publish_gate] autopublish FAILED day={day} rc={entry.get('publish_rc')}", file=sys.stderr)
    return int(entry.get("publish_rc") or 1)


def main() -> int:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

    parser = argparse.ArgumentParser(description="Discord approval gate for daily publish.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    req = sub.add_parser("request", help="Send approval request for a validated day")
    req.add_argument("--day", default=datetime.now().strftime("%Y-%m-%d"))
    req.add_argument("--force", action="store_true")

    chk = sub.add_parser("check", help="Check Discord replies and apply approvals")
    chk.add_argument("--publish", action="store_true", help="Run publish command when approved")

    retry = sub.add_parser("retry", help="Retry publish for an already approved day without re-requesting approval")
    retry.add_argument("--day", default=datetime.now().strftime("%Y-%m-%d"))

    auto = sub.add_parser("autopublish", help="Publish directly with no Discord approval (cloud daily pipeline)")
    auto.add_argument("--day", default=datetime.now().strftime("%Y-%m-%d"))
    auto.add_argument("--notify", action="store_true", help="Also post status to Discord webhook if BIZZAL_DISCORD_WEBHOOK_URL is set")

    args = parser.parse_args()

    state_file = os.getenv("BIZZAL_DISCORD_APPROVAL_STATE", "data/archive/approvals/discord_publish_gate.json")
    if not os.path.isabs(state_file):
        state_file = os.path.join(repo_root, state_file)

    webhook_url = normalize_webhook_url((os.getenv("BIZZAL_DISCORD_WEBHOOK_URL") or "").strip())

    if args.cmd == "request":
        return request_mode(repo_root, args.day.strip(), state_file, webhook_url, args.force)
    if args.cmd == "retry":
        return retry_mode(repo_root, args.day.strip(), state_file, webhook_url)
    if args.cmd == "autopublish":
        # No Discord by default; pass the webhook through only with --notify.
        auto_webhook = webhook_url if args.notify else ""
        return autopublish_mode(repo_root, args.day.strip(), state_file, auto_webhook)

    bot_token = (os.getenv("BIZZAL_DISCORD_BOT_TOKEN") or "").strip()
    channel_id = normalize_discord_id((os.getenv("BIZZAL_DISCORD_CHANNEL_ID") or "").strip())
    approved = (os.getenv("BIZZAL_DISCORD_APPROVER_USER_IDS") or "").strip()
    approve_users = {normalize_discord_id(x.strip()) for x in approved.split(",") if normalize_discord_id(x.strip())}
    return check_mode(repo_root, state_file, bot_token, channel_id, approve_users, webhook_url, args.publish)


if __name__ == "__main__":
    raise SystemExit(main())
