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


def is_upload_limit_exceeded_error(exc: Exception) -> bool:
    txt = str(exc).lower()
    return "uploadlimitexceeded" in txt or "exceeded the number of videos they may upload" in txt


def oauth_noninteractive_mode() -> bool:
    raw = (os.getenv("BIZZAL_YT_NONINTERACTIVE") or os.getenv("BIZZAL_YT_AUTH_NONINTERACTIVE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def youtube_auth_paths() -> tuple[Path, Path]:
    client_secrets = Path((os.getenv("BIZZAL_YT_CLIENT_SECRETS") or "~/.config/bizzal/youtube_client_secrets.json")).expanduser()
    token_file = Path((os.getenv("BIZZAL_YT_TOKEN_FILE") or "~/.config/bizzal/youtube_token.json")).expanduser()
    return client_secrets, token_file


def load_atom(repo_root: Path, day: str) -> dict:
    validated_dir_raw = (os.getenv("BIZZAL_ATOM_VALIDATED_DIR") or "data/atoms/validated").strip()
    validated_dir = Path(validated_dir_raw).expanduser()
    if not validated_dir.is_absolute():
        validated_dir = repo_root / validated_dir
    atom_path = validated_dir / f"{day}.json"
    if not atom_path.is_file():
        raise FileNotFoundError(f"validated atom missing: {atom_path}")
    return json.loads(atom_path.read_text(encoding="utf-8"))


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def publish_registry_path(repo_root: Path) -> Path:
    val = (os.getenv("BIZZAL_PUBLISH_REGISTRY") or "data/archive/publish/published_registry.json").strip()
    p = Path(val).expanduser()
    if not p.is_absolute():
        p = repo_root / p
    return p


def approval_state_path(repo_root: Path) -> Path:
    val = (os.getenv("BIZZAL_DISCORD_APPROVAL_STATE") or "data/archive/approvals/discord_publish_gate.json").strip()
    p = Path(val).expanduser()
    if not p.is_absolute():
        p = repo_root / p
    return p


def default_video_path_for_day(repo_root: Path, day: str) -> Path:
    by_day_dir_raw = (os.getenv("BIZZAL_RENDERS_BY_DAY_DIR") or "data/renders/by_day").strip()
    by_day_dir = Path(by_day_dir_raw).expanduser()
    if not by_day_dir.is_absolute():
        by_day_dir = repo_root / by_day_dir

    day_video = by_day_dir / f"{day}.mp4"
    if day_video.is_file():
        return day_video

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    allow_latest_fallback = (os.getenv("BIZZAL_UPLOAD_ALLOW_LATEST_FALLBACK") or "0").strip() == "1"
    if day != today and not allow_latest_fallback:
        raise FileNotFoundError(
            f"day-specific video missing for historical publish: {day_video}. "
            "Refusing fallback to latest.mp4; set BIZZAL_UPLOAD_ALLOW_LATEST_FALLBACK=1 to override."
        )

    latest_raw = (os.getenv("BIZZAL_LATEST_VIDEO_PATH") or "data/renders/latest/latest.mp4").strip()
    latest_path = Path(latest_raw).expanduser()
    if not latest_path.is_absolute():
        latest_path = repo_root / latest_path
    return latest_path


def load_registry(path: Path) -> dict:
    if not path.is_file():
        return {"items": []}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict) and isinstance(obj.get("items"), list):
            return obj
    except Exception:
        pass
    return {"items": []}


def load_approval_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def save_registry(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def build_publish_fingerprint(atom: dict, day: str, video_path: Path, video_sha256: str) -> dict:
    content = atom.get("content") or {}
    script = atom.get("script") or {}
    fact = atom.get("fact") or {}
    fingerprint = {
        "day": day,
        "category": atom.get("category") or "",
        "angle": atom.get("angle") or "",
        "content_id": content.get("content_id") or "",
        "canonical_hash": content.get("canonical_hash") or "",
        "script_id": atom.get("script_id") or content.get("script_id") or "",
        "fact_kind": fact.get("kind") or "",
        "fact_pk": fact.get("pk"),
        "fact_name": (fact.get("name") or "").strip(),
        "hook": (script.get("hook") or "").strip(),
        "body": (script.get("body") or "").strip(),
        "cta": (script.get("cta") or "").strip(),
        "video_path": str(video_path),
        "video_sha256": video_sha256,
    }
    packed = json.dumps(fingerprint, sort_keys=True, ensure_ascii=False)
    fingerprint_hash = hashlib.sha256(packed.encode("utf-8")).hexdigest()
    return {
        "hash": fingerprint_hash,
        "fingerprint": fingerprint,
    }


def duplicate_publish(registry: dict, publish_hash: str, content_id: str) -> dict | None:
    for item in registry.get("items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("publish_hash") == publish_hash:
            return item
        if content_id and item.get("content_id") == content_id:
            return item
    return None


def build_title(atom: dict, day: str) -> str:
    fact = atom.get("fact") or {}
    name = (fact.get("name") or "Daily RPG Tip").strip()
    category = (atom.get("category") or "rpg_short").replace("_", " ").title()
    profile = content_profile(atom)
    hashline = "#shadowdark #osr #shorts" if profile == "shadowdark" else "#dnd #ttrpg #shorts"
    title = f"{name} • {category} {hashline}"
    return title[:100]


def build_description(atom: dict, day: str) -> str:
    script = atom.get("script") or {}
    hook = (script.get("hook") or "").strip()
    body = (script.get("body") or "").strip()
    cta = (script.get("cta") or "").strip()
    category = (atom.get("category") or "").strip()
    angle = (atom.get("angle") or "").strip()
    profile = content_profile(atom)
    hashtags = "#shadowdark #osr #ttrpg #shorts" if profile == "shadowdark" else "#dnd #dnd5e #ttrpg #shorts"
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
        hashtags,
    ]
    return "\n".join(x for x in lines if x is not None)[:5000]


def content_profile(atom: dict) -> str:
    label = (os.getenv("BIZZAL_CHAIN_LABEL") or "").strip().lower()
    if label in {"shadowdark", "sd"}:
        return "shadowdark"

    source = atom.get("source") or {}
    active_srd_path = str(source.get("active_srd_path") or "").lower()
    if "shadowdark" in active_srd_path:
        return "shadowdark"

    fact = atom.get("fact") or {}
    document = str(fact.get("document") or "").lower()
    if "shadowdark" in document:
        return "shadowdark"

    return "dnd"


def youtube_tags_for_profile(profile: str) -> list[str]:
    if profile == "shadowdark":
        return ["shadowdark", "osr", "ttrpg", "shorts", "dungeon", "rpg"]
    return ["dnd", "dnd5e", "ttrpg", "shorts"]


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
            if oauth_noninteractive_mode():
                raise RuntimeError(
                    "YouTube OAuth requires interactive re-auth, but non-interactive mode is enabled. "
                    "Run bin/upload/upload_youtube.py --refresh-auth-only in an interactive shell to repair auth."
                )
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
                    auth_url, _ = flow.authorization_url(
                        access_type="offline",
                        include_granted_scopes="true",
                        prompt="consent",
                    )
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


def upload_video(
    youtube,
    video_path: Path,
    title: str,
    description: str,
    privacy: str,
    category_id: str,
    tags: list[str],
):
    from googleapiclient.http import MediaFileUpload

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": category_id,
            "tags": tags,
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
    parser.add_argument("--refresh-auth-only", action="store_true", help="Refresh or create the YouTube OAuth token without uploading")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    client_secrets, token_file = youtube_auth_paths()

    if args.refresh_auth_only:
        try:
            get_youtube_service(client_secrets, token_file)
        except Exception as exc:
            if is_oauth_invalid_grant_error(exc):
                eprint(
                    "ERROR: upload auth failed (invalid_grant: token expired or revoked). "
                    f"Re-auth required for token file: {token_file}"
                )
                return 9
            eprint(f"ERROR: auth refresh failed: {exc}")
            return 4
        print(f"[upload_youtube] auth ok token={token_file}")
        return 0

    day = args.day.strip()
    if not day:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        default_video_path = default_video_path_for_day(repo_root, day)
    except FileNotFoundError as exc:
        eprint(f"ERROR: {exc}")
        return 2
    video_path = Path(args.video).expanduser() if args.video else default_video_path
    if not video_path.is_file():
        eprint(f"ERROR: video not found: {video_path}")
        return 2

    try:
        atom = load_atom(repo_root, day)
    except Exception as exc:
        eprint(f"ERROR: unable to load atom for day {day}: {exc}")
        return 3

    video_sha = sha256_file(video_path)
    fp = build_publish_fingerprint(atom, day, video_path, video_sha)
    publish_hash = fp["hash"]
    fingerprint = fp["fingerprint"]
    content_id = str(((atom.get("content") or {}).get("content_id") or "")).strip()

    approval_file = approval_state_path(repo_root)
    approval_state = load_approval_state(approval_file)
    approval_entry = ((approval_state.get("approvals") or {}).get(day) or {}) if isinstance(approval_state, dict) else {}
    approval_status = str(approval_entry.get("status") or "").strip().lower()
    approval_content_id = str(approval_entry.get("content_id") or "").strip()
    if approval_status not in {"approved", "published"}:
        eprint(
            "ERROR: publish blocked; Discord approval required. "
            f"day={day} status={approval_status or '(missing)'} state_file={approval_file}"
        )
        return 7
    if content_id and approval_content_id and approval_content_id != content_id:
        eprint(
            "ERROR: publish blocked; approval content mismatch. "
            f"day={day} approved_content_id={approval_content_id} atom_content_id={content_id}"
        )
        return 8

    registry_file = publish_registry_path(repo_root)
    registry = load_registry(registry_file)
    prior = duplicate_publish(registry, publish_hash, content_id)
    if prior:
        prior_vid = str(prior.get("youtube_video_id") or "")
        prior_url = f"https://www.youtube.com/watch?v={prior_vid}" if prior_vid else "(unknown)"
        eprint(
            "ERROR: duplicate publish blocked. "
            f"day={day} content_id={content_id or '(none)'} hash={publish_hash[:16]} prior_video={prior_url}"
        )
        eprint("Duplicate override is disabled by policy.")
        return 6

    title = build_title(atom, day)
    description = build_description(atom, day)
    privacy = (os.getenv("BIZZAL_YT_PRIVACY") or "private").strip().lower()
    if privacy not in {"private", "unlisted", "public"}:
        privacy = "private"
    category_id = (os.getenv("BIZZAL_YT_CATEGORY_ID") or "20").strip()  # Gaming

    try:
        youtube = get_youtube_service(client_secrets, token_file)
        profile = content_profile(atom)
        response = upload_video(
            youtube,
            video_path,
            title,
            description,
            privacy,
            category_id,
            youtube_tags_for_profile(profile),
        )
    except Exception as exc:
        if is_oauth_invalid_grant_error(exc):
            eprint(
                "ERROR: upload auth failed (invalid_grant: token expired or revoked). "
                f"Re-auth required for token file: {token_file}"
            )
            return 9
        if is_upload_limit_exceeded_error(exc):
            eprint(
                "ERROR: upload blocked (upload limit exceeded). "
                "Pause retries and resume after the YouTube account/channel upload window resets."
            )
            eprint(f"DETAIL: {exc}")
            return 14
        eprint(f"ERROR: upload failed: {exc}")
        return 4

    vid = str(response.get("id") or "")
    if not vid:
        eprint("ERROR: upload returned no video id")
        return 5

    print(f"[upload_youtube] uploaded id={vid} privacy={privacy} file={video_path}")
    print(f"https://www.youtube.com/watch?v={vid}")

    registry.setdefault("items", [])
    registry["items"].append(
        {
            "published_utc": utc_now(),
            "day": day,
            "content_id": content_id,
            "publish_hash": publish_hash,
            "youtube_video_id": vid,
            "youtube_url": f"https://www.youtube.com/watch?v={vid}",
            "video_sha256": video_sha,
            "video_path": str(video_path),
            "fingerprint": fingerprint,
        }
    )
    save_registry(registry_file, registry)
    print(f"[upload_youtube] registry={registry_file} hash={publish_hash[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
