#!/usr/bin/env python3
import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from urllib import error
from urllib import request


def parse_health_line(output: str) -> dict:
    line = ""
    for candidate in output.strip().splitlines():
        if candidate.startswith("PIPELINE_HEALTH "):
            line = candidate.strip()
    if not line:
        return {"overall": "RED", "raw": output.strip(), "parse_error": "missing_health_line"}

    parts = line.split()
    data = {"overall": parts[1] if len(parts) > 1 else "RED", "raw": line}
    for token in parts[2:]:
        if "=" in token:
            key, value = token.split("=", 1)
            data[key] = value
    return data


def run_health_check(repo_root: str, month: str | None) -> tuple[int, str, dict]:
    cmd = [os.path.join(repo_root, "bin", "core", "pipeline_health_check.sh")]
    if month:
        cmd.extend(["--month", month])
    proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    parsed = parse_health_line(output)
    return proc.returncode, output.strip(), parsed


def build_payload(host: str, month_label: str, health_rc: int, health: dict, health_output: str) -> dict:
    overall = (health.get("overall") or "RED").upper()
    icon = "🟢" if overall == "GREEN" else "🔴"
    color = 0x2ECC71 if overall == "GREEN" else 0xE74C3C
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    fields = [
        {"name": "Host", "value": host, "inline": True},
        {"name": "Month", "value": month_label, "inline": True},
        {"name": "Overall", "value": overall, "inline": True},
        {"name": "Daily", "value": health.get("daily", "unknown"), "inline": True},
        {"name": "Monthly", "value": health.get("monthly", "unknown"), "inline": True},
        {"name": "Exit Code", "value": str(health_rc), "inline": True},
    ]

    details = health.get("raw", "")
    if len(details) > 1000:
        details = details[:1000] + "..."
    output_short = health_output.strip()
    if len(output_short) > 1000:
        output_short = output_short[:1000] + "..."

    embed = {
        "title": f"{icon} Bizzal Pipeline Health",
        "description": f"Status check for `{month_label}`",
        "color": color,
        "fields": fields,
        "footer": {"text": f"UTC {now_utc}"},
    }
    if details:
        embed["fields"].append({"name": "Health Line", "value": f"```{details}```", "inline": False})
    if output_short and output_short != details:
        embed["fields"].append({"name": "Output", "value": f"```{output_short}```", "inline": False})

    return {
        "username": "Bizzal Pipeline Bot",
        "embeds": [embed],
    }


def post_webhook(webhook_url: str, payload: dict):
    webhook_url = webhook_url.replace("https://discordapp.com/", "https://discord.com/")
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "BizzalPipelineBot/1.0 (+https://github.com/bizzal70/Bizzal-Games-YT-PUB)",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            _ = resp.read()
        return
    except error.HTTPError as exc:
        if exc.code not in {401, 403}:
            raise

    curl_cmd = [
        "curl",
        "-sS",
        "-o",
        "/tmp/bizzal_discord_webhook_resp.txt",
        "-w",
        "%{http_code}",
        "-X",
        "POST",
        webhook_url,
        "-H",
        "Content-Type: application/json",
        "--data-binary",
        json.dumps(payload),
    ]
    proc = subprocess.run(curl_cmd, capture_output=True, text=True)
    status = (proc.stdout or "").strip()
    if status.startswith("2"):
        return

    body = ""
    try:
        with open("/tmp/bizzal_discord_webhook_resp.txt", "r", encoding="utf-8") as f:
            body = f.read().strip()
    except OSError:
        body = ""
    raise RuntimeError(f"discord webhook rejected: http={status or 'unknown'} body={body or '(empty)'}")


def main() -> int:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    parser = argparse.ArgumentParser(description="Send RED/GREEN pipeline health notification to Discord webhook.")
    parser.add_argument("--month", default=os.getenv("BIZZAL_HEALTH_MONTH", ""), help="Optional month filter (YYYY-MM)")
    parser.add_argument("--webhook-url", default=os.getenv("BIZZAL_DISCORD_WEBHOOK_URL", ""))
    parser.add_argument("--dry-run", action="store_true", help="Print payload without sending")
    args = parser.parse_args()

    month = args.month.strip() or None
    month_label = month or "latest"
    webhook_url = args.webhook_url.strip()

    health_rc, health_output, health = run_health_check(repo_root, month)
    host = socket.gethostname()
    payload = build_payload(host, month_label, health_rc, health, health_output)

    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0 if (health.get("overall") or "RED").upper() == "GREEN" else 1

    if not webhook_url:
        print("ERROR: missing webhook URL (set BIZZAL_DISCORD_WEBHOOK_URL or use --webhook-url)", file=sys.stderr)
        return 2

    try:
        post_webhook(webhook_url, payload)
    except Exception as exc:
        print(f"ERROR: webhook post failed: {exc}", file=sys.stderr)
        return 3

    overall = (health.get("overall") or "RED").upper()
    print(f"[pipeline_health_discord] sent overall={overall} month={month_label}")
    return 0 if overall == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
