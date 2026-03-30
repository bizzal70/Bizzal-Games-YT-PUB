#!/usr/bin/env python3
import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from urllib import error, request


def load_env_file(path: str):
    if not path or not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value


def normalize_webhook_url(url: str) -> str:
    txt = (url or "").strip()
    if len(txt) >= 2 and txt[0] == txt[-1] and txt[0] in {"'", '"'}:
        txt = txt[1:-1].strip()
    txt = txt.replace("https://discordapp.com/", "https://discord.com/")
    txt = txt.replace("http://discordapp.com/", "https://discord.com/")
    return txt


def run_probe(repo_root: str) -> tuple[int, str]:
    script = os.path.join(repo_root, "bin", "upload", "upload_youtube.py")
    if not os.path.isfile(script):
        return 2, f"upload script missing: {script}"

    if os.access(script, os.X_OK):
        cmd = [script, "--refresh-auth-only"]
    else:
        py = os.path.join(repo_root, ".venv", "bin", "python")
        if os.path.isfile(py):
            cmd = [py, script, "--refresh-auth-only"]
        else:
            cmd = ["python3", script, "--refresh-auth-only"]

    env = os.environ.copy()
    env["BIZZAL_YT_NONINTERACTIVE"] = "1"
    proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, env=env)
    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return proc.returncode, out


def post_webhook(webhook_url: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "BizzalYoutubeAuthProbe/1.0"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            _ = resp.read()
    except error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        raise RuntimeError(f"discord webhook rejected: http={exc.code} body={detail or '(empty)'}")


def main() -> int:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    parser = argparse.ArgumentParser(description="Probe YouTube auth refresh and alert Discord on failures")
    parser.add_argument("--env-file", default=os.getenv("BIZZAL_ENV_FILE", os.path.expanduser("~/.config/bizzal.env")))
    parser.add_argument("--webhook-url", default=os.getenv("BIZZAL_DISCORD_WEBHOOK_URL", ""))
    parser.add_argument("--post-ok", action="store_true", help="Also post success messages")
    parser.add_argument("--dry-run", action="store_true", help="Print result only; do not post webhook")
    args = parser.parse_args()

    load_env_file(args.env_file)
    webhook_url = normalize_webhook_url(args.webhook_url or os.getenv("BIZZAL_DISCORD_WEBHOOK_URL", ""))

    rc, output = run_probe(repo_root)
    host = socket.gethostname()
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    first = ""
    for line in output.splitlines():
        txt = line.strip()
        if txt:
            first = txt
            break

    if rc == 0:
        print(f"[youtube_auth_probe] ok host={host}")
        if not args.post_ok or args.dry_run or not webhook_url:
            return 0
        post_webhook(
            webhook_url,
            {
                "username": "Bizzal Ops Bot",
                "content": f"✅ Weekly YouTube auth probe OK on `{host}` at `{now_utc}`.",
            },
        )
        return 0

    severity = "auth"
    if rc == 9:
        headline = "YouTube auth probe failed: invalid_grant"
        detail = first or "token expired or revoked"
    else:
        headline = f"YouTube auth probe failed (rc={rc})"
        detail = first or "unknown error"
        severity = "runtime"

    print(f"[youtube_auth_probe] FAIL rc={rc} host={host} detail={detail}")
    if args.dry_run or not webhook_url:
        return rc if rc != 0 else 1

    post_webhook(
        webhook_url,
        {
            "username": "Bizzal Ops Bot",
            "content": (
                f"🚨 {headline} on `{host}` at `{now_utc}`.\n"
                f"severity={severity}\n"
                f"detail={detail}\n"
                "Run: `rm -f ~/.config/bizzal/youtube_token.json && bin/upload/upload_youtube.py --refresh-auth-only`"
            ),
        },
    )
    return rc if rc != 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())