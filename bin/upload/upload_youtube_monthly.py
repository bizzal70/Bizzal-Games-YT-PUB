#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def eprint(msg: str):
    print(msg, file=sys.stderr)


def is_oauth_invalid_grant_error(exc: Exception) -> bool:
    txt = str(exc).lower()
    return "invalid_grant" in txt or "token has been expired or revoked" in txt


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def monthly_video_path(repo_root: Path, month: str) -> Path:
    return repo_root / "data" / "archive" / "monthly" / month / f"monthly_longform_{month}.mp4"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def approval_state_path(repo_root: Path) -> Path:
    val = (os.getenv("BIZZAL_DISCORD_MONTHLY_APPROVAL_STATE") or "data/archive/approvals/discord_monthly_publish_gate.json").strip()
    p = Path(val).expanduser()
    if not p.is_absolute():
        p = repo_root / p
    return p


def publish_registry_path(repo_root: Path) -> Path:
    val = (os.getenv("BIZZAL_MONTHLY_PUBLISH_REGISTRY") or "data/archive/publish/published_monthly_registry.json").strip()
    p = Path(val).expanduser()
    if not p.is_absolute():
        p = repo_root / p
    return p


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def load_registry(path: Path) -> dict:
    obj = load_json(path)
    if isinstance(obj.get("items"), list):
        return obj
    return {"items": []}


def save_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def duplicate_publish(registry: dict, publish_hash: str, month: str) -> dict | None:
    for item in registry.get("items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("publish_hash") == publish_hash:
            return item
        if item.get("month") == month:
            return item
    return None


def get_youtube_service(client_secrets: Path, token_file: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except Exception as exc:
        raise RuntimeError(
            "Missing YouTube dependencies. Install: python3 -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2"
        ) from exc

    scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]
    creds = None

    if token_file.is_file():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = None
            if client_secrets.is_file():
                flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), scopes)
            else:
                client_id = (os.getenv("BIZZAL_YT_CLIENT_ID") or "").strip()
                client_secret = (os.getenv("BIZZAL_YT_CLIENT_SECRET") or "").strip()
                if client_id and client_secret:
                    client_config = {
                        "installed": {
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "redirect_uris": [
                                "http://localhost",
                                "http://localhost:8080/",
                                "urn:ietf:wg:oauth:2.0:oob",
                            ],
                        }
                    }
                    flow = InstalledAppFlow.from_client_config(client_config, scopes)
                else:
                    raise FileNotFoundError(
                        f"YouTube client secrets not found: {client_secrets}. Set file OR env vars BIZZAL_YT_CLIENT_ID and BIZZAL_YT_CLIENT_SECRET."
                    )

            oauth_mode = (os.getenv("BIZZAL_YT_OAUTH_MODE") or "console").strip().lower()
            if oauth_mode == "local":
                creds = flow.run_local_server(port=0)
            else:
                if hasattr(flow, "run_console"):
                    creds = flow.run_console()
                else:
                    flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
                    auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
                    print("Open this URL in a browser and complete authorization:")
                    print(auth_url)
                    code = input("Paste the authorization code here: ").strip()
                    if not code:
                        raise RuntimeError("No authorization code provided")
                    flow.fetch_token(code=code)
                    creds = flow.credentials

        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=creds)


def upload_video(youtube, video_path: Path, title: str, description: str, privacy: str, category_id: str):
    from googleapiclient.http import MediaFileUpload

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": category_id,
            "tags": ["dnd", "ttrpg", "longform", "dnd5e", "bizzal"],
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
    )

    response = None
    while response is None:
        _, response = request.next_chunk()

    return response


def build_title(month: str) -> str:
    return f"Bizzal RPG Monthly Longform • {month} #dnd #ttrpg"


def build_description(month: str) -> str:
    return "\n".join(
        [
            f"Bizzal Monthly Longform • {month}",
            "",
            "Compilation of approved daily shorts for the month.",
            "",
            "#dnd #dnd5e #ttrpg",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload monthly longform video to YouTube")
    parser.add_argument("--month", default=datetime.utcnow().strftime("%Y-%m"), help="Month YYYY-MM")
    parser.add_argument("--video", default="", help="Video path override")
    args = parser.parse_args()

    month = args.month.strip()
    if len(month) != 7 or month[4] != "-":
        eprint("ERROR: --month must be YYYY-MM")
        return 2

    repo_root = Path(__file__).resolve().parents[2]
    video_path = Path(args.video).expanduser() if args.video else monthly_video_path(repo_root, month)
    if not video_path.is_file():
        eprint(f"ERROR: monthly video not found: {video_path}")
        return 3

    approval_file = approval_state_path(repo_root)
    approval_state = load_json(approval_file)
    entry = ((approval_state.get("approvals") or {}).get(month) or {}) if isinstance(approval_state, dict) else {}
    status = str(entry.get("status") or "").strip().lower()
    if status not in {"approved", "published"}:
        eprint(
            "ERROR: monthly publish blocked; Discord approval required. "
            f"month={month} status={status or '(missing)'} state_file={approval_file}"
        )
        return 7

    video_sha = sha256_file(video_path)
    packed = json.dumps({"month": month, "video_sha256": video_sha, "video_path": str(video_path)}, sort_keys=True)
    publish_hash = hashlib.sha256(packed.encode("utf-8")).hexdigest()

    registry_file = publish_registry_path(repo_root)
    registry = load_registry(registry_file)
    prior = duplicate_publish(registry, publish_hash, month)
    if prior:
        prior_vid = str(prior.get("youtube_video_id") or "")
        prior_url = f"https://www.youtube.com/watch?v={prior_vid}" if prior_vid else "(unknown)"
        eprint(f"ERROR: duplicate monthly publish blocked month={month} prior_video={prior_url}")
        return 6

    title = build_title(month)
    description = build_description(month)
    privacy = (os.getenv("BIZZAL_YT_MONTHLY_PRIVACY") or os.getenv("BIZZAL_YT_PRIVACY") or "private").strip().lower()
    if privacy not in {"private", "unlisted", "public"}:
        privacy = "private"
    category_id = (os.getenv("BIZZAL_YT_CATEGORY_ID") or "20").strip()

    client_secrets = Path((os.getenv("BIZZAL_YT_CLIENT_SECRETS") or "~/.config/bizzal/youtube_client_secrets.json")).expanduser()
    token_file = Path((os.getenv("BIZZAL_YT_TOKEN_FILE") or "~/.config/bizzal/youtube_token.json")).expanduser()

    try:
        youtube = get_youtube_service(client_secrets, token_file)
        response = upload_video(youtube, video_path, title, description, privacy, category_id)
    except Exception as exc:
        if is_oauth_invalid_grant_error(exc):
            eprint(
                "ERROR: monthly upload auth failed (invalid_grant: token expired or revoked). "
                f"Re-auth required for token file: {token_file}"
            )
            return 9
        eprint(f"ERROR: monthly upload failed: {exc}")
        return 4

    vid = str(response.get("id") or "")
    if not vid:
        eprint("ERROR: monthly upload returned no video id")
        return 5

    print(f"[upload_youtube_monthly] uploaded month={month} id={vid} privacy={privacy} file={video_path}")
    print(f"https://www.youtube.com/watch?v={vid}")

    registry.setdefault("items", [])
    registry["items"].append(
        {
            "published_utc": utc_now(),
            "month": month,
            "publish_hash": publish_hash,
            "youtube_video_id": vid,
            "youtube_url": f"https://www.youtube.com/watch?v={vid}",
            "video_sha256": video_sha,
            "video_path": str(video_path),
        }
    )
    save_json(registry_file, registry)
    print(f"[upload_youtube_monthly] registry={registry_file} hash={publish_hash[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
