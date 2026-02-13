#!/usr/bin/env python3
import argparse
import os
import shlex
import socket
import ssl
import subprocess
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
import smtplib


def parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


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


def send_email(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    use_starttls: bool,
    use_ssl: bool,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
):
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    if use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=30) as server:
            if smtp_user:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        if use_starttls:
            context = ssl.create_default_context()
            server.starttls(context=context)
        if smtp_user:
            server.login(smtp_user, smtp_pass)
        server.send_message(msg)


def main() -> int:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

    parser = argparse.ArgumentParser(description="Send RED/GREEN pipeline health email.")
    parser.add_argument("--month", default=os.getenv("BIZZAL_HEALTH_MONTH", ""), help="Optional month filter (YYYY-MM)")
    parser.add_argument("--to", dest="to_addr", default=os.getenv("BIZZAL_ALERT_EMAIL_TO", "bizzalgames70@gmail.com"))
    parser.add_argument("--from", dest="from_addr", default=os.getenv("BIZZAL_ALERT_EMAIL_FROM", ""))
    parser.add_argument("--dry-run", action="store_true", help="Print email content without sending")
    args = parser.parse_args()

    month = args.month.strip() or None
    to_addr = args.to_addr.strip()
    from_addr = args.from_addr.strip() or to_addr

    smtp_host = os.getenv("BIZZAL_SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("BIZZAL_SMTP_PORT", "587"))
    smtp_user = os.getenv("BIZZAL_SMTP_USER", "").strip()
    smtp_pass = os.getenv("BIZZAL_SMTP_PASS", "")
    use_starttls = parse_bool_env("BIZZAL_SMTP_STARTTLS", True)
    use_ssl = parse_bool_env("BIZZAL_SMTP_SSL", False)

    health_rc, health_output, health = run_health_check(repo_root, month)
    overall = (health.get("overall") or "RED").upper()
    host = socket.gethostname()
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    month_label = month or "latest"

    subject = f"[Bizzal Pipeline] {overall} | {host} | {month_label}"
    body = "\n".join(
        [
            f"utc={now_utc}",
            f"host={host}",
            f"repo={repo_root}",
            f"month={month_label}",
            f"overall={overall}",
            f"health_exit_code={health_rc}",
            f"health_line={health.get('raw', '')}",
            "",
            "health_output:",
            health_output,
        ]
    ).rstrip() + "\n"

    if args.dry_run:
        print("[pipeline_health_email] dry-run mode")
        print(f"[pipeline_health_email] to={to_addr}")
        print(f"[pipeline_health_email] from={from_addr}")
        print(f"[pipeline_health_email] subject={subject}")
        print(body)
        return 0 if overall == "GREEN" else 1

    missing = []
    if not smtp_host:
        missing.append("BIZZAL_SMTP_HOST")
    if smtp_user and not smtp_pass:
        missing.append("BIZZAL_SMTP_PASS")
    if missing:
        print(f"ERROR: missing required SMTP env vars: {', '.join(missing)}", file=sys.stderr)
        return 2

    try:
        send_email(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_pass=smtp_pass,
            use_starttls=use_starttls,
            use_ssl=use_ssl,
            from_addr=from_addr,
            to_addr=to_addr,
            subject=subject,
            body=body,
        )
    except Exception as exc:
        print(f"ERROR: email send failed: {exc}", file=sys.stderr)
        return 3

    print(f"[pipeline_health_email] sent to={to_addr} subject={subject}")
    return 0 if overall == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
