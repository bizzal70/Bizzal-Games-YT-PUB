#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path


def eprint(msg: str):
    print(msg, file=sys.stderr)


def load_atom(repo_root: Path, day: str) -> dict:
    atom_path = repo_root / "data" / "atoms" / "validated" / f"{day}.json"
    if not atom_path.is_file():
        raise FileNotFoundError(f"validated atom missing: {atom_path}")
    return json.loads(atom_path.read_text(encoding="utf-8"))


def build_title(atom: dict, day: str) -> str:
    fact = atom.get("fact") or {}
    name = (fact.get("name") or "Daily RPG Tip").strip()
    category = (atom.get("category") or "rpg_short").replace("_", " ").title()
    title = f"{name} • {category} #dnd #ttrpg #shorts"
    return title[:100]


def build_description(atom: dict, day: str) -> str:
    script = atom.get("script") or {}
    hook = (script.get("hook") or "").strip()
    body = (script.get("body") or "").strip()
    cta = (script.get("cta") or "").strip()
    category = (atom.get("category") or "").strip()
    angle = (atom.get("angle") or "").strip()
    lines = [
        f"Daily RPG Short • {day}",
        "",
        hook,
        "",
        body,
        "",
        cta,
        "",
        f"category: {category}",
        f"angle: {angle}",
        "",
        "#dnd #dnd5e #ttrpg #shorts",
    ]
    return "\n".join(x for x in lines if x is not None)[:5000]


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

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
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
                creds = flow.run_console()

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
            "tags": ["dnd", "ttrpg", "shorts", "dnd5e"],
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload latest rendered short to YouTube")
    parser.add_argument("--day", default=os.getenv("BIZZAL_DAY", ""), help="Day YYYY-MM-DD (default: today inferred by render path)")
    parser.add_argument("--video", default="", help="Video path (default: data/renders/latest/latest.mp4)")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    day = args.day.strip()
    if not day:
        from datetime import datetime

        day = datetime.utcnow().strftime("%Y-%m-%d")

    video_path = Path(args.video).expanduser() if args.video else (repo_root / "data" / "renders" / "latest" / "latest.mp4")
    if not video_path.is_file():
        eprint(f"ERROR: video not found: {video_path}")
        return 2

    try:
        atom = load_atom(repo_root, day)
    except Exception as exc:
        eprint(f"ERROR: unable to load atom for day {day}: {exc}")
        return 3

    title = build_title(atom, day)
    description = build_description(atom, day)
    privacy = (os.getenv("BIZZAL_YT_PRIVACY") or "private").strip().lower()
    if privacy not in {"private", "unlisted", "public"}:
        privacy = "private"
    category_id = (os.getenv("BIZZAL_YT_CATEGORY_ID") or "20").strip()  # Gaming

    client_secrets = Path((os.getenv("BIZZAL_YT_CLIENT_SECRETS") or "~/.config/bizzal/youtube_client_secrets.json")).expanduser()
    token_file = Path((os.getenv("BIZZAL_YT_TOKEN_FILE") or "~/.config/bizzal/youtube_token.json")).expanduser()

    try:
        youtube = get_youtube_service(client_secrets, token_file)
        response = upload_video(youtube, video_path, title, description, privacy, category_id)
    except Exception as exc:
        eprint(f"ERROR: upload failed: {exc}")
        return 4

    vid = str(response.get("id") or "")
    if not vid:
        eprint("ERROR: upload returned no video id")
        return 5

    print(f"[upload_youtube] uploaded id={vid} privacy={privacy} file={video_path}")
    print(f"https://www.youtube.com/watch?v={vid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
