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


def _hook_fragment(hook: str, limit: int = 80) -> str:
    """Pull a short, punchy curiosity fragment out of the (full-sentence) hook.

    The hook is a whole sentence like "Yes, Cubi Devil looks harmless - until the
    table underestimates it and gives it free turns." For a title we want the
    tension, not the whole thing, so take the clause before the first dash/colon/
    period, drop a leading "Yes,"/"No,", and trim to a title-friendly length on a
    word boundary. Returns "" if nothing usable is left.
    """
    import re

    frag = re.split(r"\s+[-—:]\s+|(?<=[.!?])\s+", hook.strip(), maxsplit=1)[0].strip()
    frag = re.sub(r"^(?:yes|no|and|but|so),?\s+", "", frag, flags=re.IGNORECASE).strip()
    frag = frag.rstrip(".!,;: ")
    if len(frag) > limit:
        # Prefer trimming at a comma clause-break within the limit over a blind
        # word-boundary cut, which can leave a technically-valid but incomplete-
        # reading fragment (e.g. "...once per" instead of "...as mist").
        comma_split = re.split(r",\s+", frag[:limit], maxsplit=1)
        if len(comma_split) > 1 and len(comma_split[0]) >= 20:
            frag = comma_split[0].rstrip(".!,;: ")
        else:
            frag = frag[:limit].rsplit(" ", 1)[0].rstrip(".!,;: ")
    return frag


def build_title(atom: dict, day: str) -> str:
    """Hook-first title: lead with the tension, keep the entity name for search.

    Was "Name • Category" (a label with no hook). Now "Hook fragment • Name" so
    the first words do curiosity work, e.g. "Free turns for free • Cubi Devil".
    Falls back to the old shape if no usable hook fragment exists.
    """
    fact = atom.get("fact") or {}
    name = (fact.get("name") or "Daily RPG Tip").strip()
    category = (atom.get("category") or "rpg_short").replace("_", " ").title()
    script = atom.get("script") or {}
    frag = _hook_fragment((script.get("hook") or "").strip())
    if frag and name.lower() not in frag.lower():
        title = f"{frag} • {name}"
    elif frag:
        title = frag
    else:
        title = f"{name} • {category}"
    if len(title) > 100:
        title = title[:100].rsplit(" ", 1)[0].rstrip(".!,;: ")
    return title


def build_description(atom: dict, day: str) -> str:
    """Description tuned for retention (line 1 hook), search (line 2 keywords),
    and subscriber growth (explicit CTA + next-up + subscribe).

    The visible feed/preview shows only the first ~150 chars, so the hook and a
    keyword-front-loaded summary lead; the full body follows; then a real CTA.
    """
    script = atom.get("script") or {}
    fact = atom.get("fact") or {}
    hook = (script.get("hook") or "").strip()
    body = (script.get("body") or "").strip()
    cta = (script.get("cta") or "").strip()
    name = (fact.get("name") or "").strip()
    category = (atom.get("category") or "").strip()
    category_label = category.replace("_", " ")
    angle = (atom.get("angle") or "").strip()
    profile = content_profile(atom)
    hashtags = hashtags_for(profile)["desc"]
    topic_tag = extract_topic_tag(f"{hook} {body}")
    if topic_tag and topic_tag not in hashtags:
        hashtags = f"{hashtags} {topic_tag}"

    # Line 2: keyword-front-loaded summary for search (name + system + topic).
    system_label = {"dnd5e": "D&D 5e", "shadowdark": "Shadowdark", "dcc": "DCC"}.get(
        profile, "TTRPG"
    )
    keyword_bits = [b for b in (name, system_label, category_label) if b]
    keyword_line = " · ".join(keyword_bits)

    # Explicit CTA block — the single biggest gap the content review flagged.
    subscribe = f"▶ Subscribe for a daily {system_label} ruling — a new short every day."
    playlist_url = (os.getenv("BIZZAL_YT_PLAYLIST_URL") or "").strip()

    lines = [
        hook or keyword_line,
        "",
        keyword_line,
        "",
        body,
        "",
        cta,
        "",
        subscribe,
    ]
    if playlist_url:
        lines.append(f"📺 More rulings: {playlist_url}")
    source_video_id = (atom.get("source_video_id") or "").strip()
    if source_video_id:
        watch = f"https://www.youtube.com/watch?v={source_video_id}"
        lines.append(f"▶ Full breakdown ({system_label}): {watch}")
    lines += [
        "",
        "Follow Bizzal Games:",
        "▶ YouTube: https://www.youtube.com/@Bizzal_Games",
        "📸 Instagram: https://www.instagram.com/bizzalgames70",
        "",
        "📖 More TTRPG rules & rulings — It's Already Written:",
        "https://bizzal70.github.io/itsalreadywritten/ · @ItsAlrdyWritten on X",
        "",
        f"category: {category}",
        f"angle: {angle}",
        "",
        hashtags,
    ]
    return "\n".join(x for x in lines if x is not None)[:5000]


# Per-system hashtag / tag sets, keyed by system id (BIZZAL_SYSTEM_ID).
# Add a row when onboarding a system; unknown systems get a neutral fallback
# rather than being mislabeled as D&D.
_HASHTAGS = {
    "dnd5e": {
        "title": "#dnd #ttrpg #shorts",
        "desc": "#dnd #dnd5e #ttrpg #shorts",
        "youtube_tags": ["dnd", "dnd5e", "ttrpg", "shorts"],
    },
    "shadowdark": {
        "title": "#shadowdark #osr #shorts",
        "desc": "#shadowdark #osr #ttrpg #shorts",
        "youtube_tags": ["shadowdark", "osr", "ttrpg", "shorts", "dungeon", "rpg"],
    },
    "dcc": {
        "title": "#dcc #osr #shorts",
        "desc": "#dcc #dungeoncrawlclassics #osr #ttrpg #shorts",
        "youtube_tags": ["dcc", "dungeon crawl classics", "osr", "ttrpg", "shorts", "rpg"],
    },
}
# One short, searchable system tag appended to every title. The new formula
# titles carry no system signal at all, so a viewer scrolling the feed cannot
# tell whether a ruling is D&D, Shadowdark or DCC -- they click the wrong game
# and bounce, or worse take the wrong ruling back to their table.
_SYSTEM_TITLE_TAG = {"dnd5e": "#dnd5e", "shadowdark": "#shadowdark", "dcc": "#dcc"}


def system_title_tag(profile: str) -> str:
    return _SYSTEM_TITLE_TAG.get(profile, "#ttrpg")


_HASHTAGS_FALLBACK = {
    "title": "#ttrpg #rpg #shorts",
    "desc": "#ttrpg #rpg #shorts",
    "youtube_tags": ["ttrpg", "rpg", "shorts"],
}


def hashtags_for(profile: str) -> dict:
    return _HASHTAGS.get(profile, _HASHTAGS_FALLBACK)


# A small, low-risk set of topic keywords -> an extra, more specific
# description hashtag. Supplements (never replaces) the static per-system set,
# and never touches the title tag (kept minimal on purpose -- see
# system_title_tag's own comment on why). YouTube's own ranking leans more on
# watch time/retention than hashtag matching, so this is a minor assist.
# Lowercase to match the static per-system hashtag set (#dnd5e, #shadowdark,
# #osr, ...) -- these used to be TitleCase (#Spells, #SavingThrow, ...) and
# stood out as an obviously auto-generated tag next to the curated set,
# flagged in the 2026-08-14 content review.
_TOPIC_TAGS = [
    ("spell", "#spells"),
    ("saving throw", "#savingthrow"),
    ("trap", "#dungeontraps"),
    ("magic item", "#magicitems"),
    ("encounter", "#encounter"),
    ("combat", "#combat"),
    ("dragon", "#dragons"),
    ("undead", "#undead"),
    ("class feature", "#classbuild"),
    ("multiclass", "#multiclass"),
]


def extract_topic_tag(text: str) -> str | None:
    low = f" {text.lower()} "
    for kw, tag in _TOPIC_TAGS:
        if kw in low:
            return tag
    return None


def content_profile(atom: dict) -> str:
    # Authoritative: the system id the daily pipeline is running under
    # (set by bin/core/system_env.sh). Returns e.g. "dnd5e" / "shadowdark" / "dcc".
    sysid = (os.getenv("BIZZAL_SYSTEM_ID") or "").strip().lower()
    if sysid:
        return sysid

    # Fallbacks for out-of-pipeline / legacy invocations.
    label = (os.getenv("BIZZAL_CHAIN_LABEL") or "").strip().lower()
    if label in {"shadowdark", "sd"}:
        return "shadowdark"
    if label == "dcc":
        return "dcc"

    source = atom.get("source") or {}
    active_srd_path = str(source.get("active_srd_path") or "").lower()
    fact = atom.get("fact") or {}
    document = str(fact.get("document") or "").lower()
    for token, prof in (("shadowdark", "shadowdark"), ("dcc", "dcc")):
        if token in active_srd_path or token in document:
            return prof

    return "dnd5e"


def youtube_tags_for_profile(profile: str) -> list[str]:
    return hashtags_for(profile)["youtube_tags"]


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
        # force-ssl is required by captions().insert to upload our own .srt track.
        # NOTE: the token materialized from BIZZAL_YT_TOKEN_JSON must have been
        # granted this scope (re-auth), or the refresh will fail "not all
        # requested scopes were granted". Deploy this only after that re-auth.
        "https://www.googleapis.com/auth/youtube.force-ssl",
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
    publish_at: str = "",
):
    from googleapiclient.http import MediaFileUpload

    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
    }
    # Scheduled release: YouTube requires the video be uploaded `private` and
    # flips it public itself at publishAt. Used to DRIP clips over following
    # days instead of dumping a long-form + all its clips in one burst (which
    # floods the feed with one topic and cannibalises its own reach).
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": category_id,
            "tags": tags,
        },
        "status": status,
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


def upload_captions(youtube, video_id: str, srt_path: Path, language: str = "en") -> None:
    """Attach an SRT caption track to an already-uploaded video.

    Requires the youtube.force-ssl scope. Callers treat failures as non-fatal:
    a missing scope or transient error must never fail the video publish.
    """
    from googleapiclient.http import MediaFileUpload

    body = {
        "snippet": {
            "videoId": video_id,
            "language": language,
            "name": "English",
            "isDraft": False,
        }
    }
    youtube.captions().insert(
        part="snippet",
        body=body,
        media_body=MediaFileUpload(str(srt_path), mimetype="application/octet-stream", resumable=False),
    ).execute()


def maybe_upload_captions(youtube, video_id: str, video_path: Path) -> None:
    """Best-effort: upload a sibling <video>.srt if present and enabled.

    Off by default so Shorts are unchanged; the long-form runner opts in via
    BIZZAL_UPLOAD_CAPTIONS=1.
    """
    if (os.getenv("BIZZAL_UPLOAD_CAPTIONS") or "0").strip().lower() in {"0", "false", "no", "off"}:
        return
    srt_path = video_path.with_suffix(".srt")
    if not srt_path.is_file():
        return
    try:
        upload_captions(youtube, video_id, srt_path)
        print(f"[upload_youtube] captions uploaded track={srt_path.name}")
    except Exception as exc:
        txt = str(exc).lower()
        if "insufficient" in txt or "forbidden" in txt or "scope" in txt:
            eprint(
                "WARN: caption upload skipped — token lacks youtube.force-ssl scope. "
                "Re-auth BIZZAL_YT_TOKEN_JSON with force-ssl. Video is unaffected."
            )
        else:
            eprint(f"WARN: caption upload failed (non-fatal): {exc}")


def set_thumbnail(youtube, video_id: str, thumb_path: Path) -> None:
    """Set a custom thumbnail on an uploaded video (needs a phone-verified
    channel). Callers treat failures as non-fatal."""
    from googleapiclient.http import MediaFileUpload

    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(str(thumb_path), mimetype="image/jpeg"),
    ).execute()


def maybe_set_thumbnail(youtube, video_id: str, video_path: Path) -> None:
    """Best-effort: set a sibling <video>.thumb.jpg custom thumbnail if enabled.

    Off by default (Shorts unchanged); the long-form runner opts in via
    BIZZAL_SET_THUMBNAIL=1. A non-eligible channel or any error never blocks
    the publish (the auto-generated frame thumbnail simply stays).
    """
    if (os.getenv("BIZZAL_SET_THUMBNAIL") or "0").strip().lower() in {"0", "false", "no", "off"}:
        return
    thumb_path = video_path.with_name(f"{video_path.stem}.thumb.jpg")
    if not thumb_path.is_file():
        return
    try:
        set_thumbnail(youtube, video_id, thumb_path)
        print(f"[upload_youtube] thumbnail set from {thumb_path.name}")
    except Exception as exc:
        txt = str(exc).lower()
        if "unauthorized" in txt or "forbidden" in txt or "verif" in txt or "not eligible" in txt:
            eprint(
                "WARN: custom thumbnail skipped — channel not eligible for custom "
                "thumbnails (needs phone verification). Video is unaffected."
            )
        else:
            eprint(f"WARN: thumbnail set failed (non-fatal): {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload latest rendered short to YouTube")
    parser.add_argument("--day", default=os.getenv("BIZZAL_DAY", ""), help="Day YYYY-MM-DD (default: today inferred by render path)")
    parser.add_argument("--video", default="", help="Video path (default: data/renders/latest/latest.mp4)")
    parser.add_argument("--refresh-auth-only", action="store_true", help="Refresh or create the YouTube OAuth token without uploading")
    parser.add_argument("--title-override", default="", help="Use this title instead of the computed one (long-form)")
    parser.add_argument("--description-override", default="", help="Use this description instead of the computed one (long-form)")
    parser.add_argument("--category-id", default="", help="YouTube category id (default: BIZZAL_YT_CATEGORY_ID or 20)")
    parser.add_argument("--not-made-for-kids", action="store_true", help="Mark selfDeclaredMadeForKids=False (already the default; accepted for the long-form caller)")
    parser.add_argument("--publish-at", default="", help="ISO8601 UTC time to auto-publish (uploads private, YouTube releases it then). Used to drip clips over days.")
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

    # Long-form passes explicit overrides; when they're blank, fall back to the
    # atom's AI-written youtube_title/description (set by write_longform_script),
    # then finally to the Shorts builders. Shorts atoms have neither override nor
    # youtube_* fields, so they keep using build_title/build_description as before.
    title = (args.title_override or "").strip() or atom.get("youtube_title") or build_title(atom, day)

    # Editorial guard: mechanically repair title defects that have shipped
    # before (the "descriptor • Subject" template artifact, titles truncated
    # mid-thought), and loudly flag anything off-formula (generic label
    # prefixes, GM-advice voice, hype) so it shows up in logs and review.
    try:
        sys.path.insert(0, str(repo_root / "bin" / "core"))
        from title_lint import lint as _title_lint

        _orig = title
        title, _issues, _ok = _title_lint(title)
        if title != _orig:
            print(f"[upload_youtube] title repaired: {_orig!r} -> {title!r}")
        if _issues:
            eprint(f"WARN: title lint flagged {_issues} on {title!r} (off-formula)")
    except Exception as exc:
        eprint(f"WARN: title lint unavailable ({exc}); using title as-is")

    # Tell the viewer which game this is. Appended AFTER the lint so it is never
    # stripped, and only when the title doesn't already name the system.
    _tag = system_title_tag(content_profile(atom))
    if _tag.lstrip("#").lower() not in title.lower():
        _candidate = f"{title} {_tag}"
        if len(_candidate) <= 100:
            title = _candidate
        else:
            budget = 100 - len(_tag) - 1
            trimmed = title[:budget].rsplit(" ", 1)[0].rstrip(".!,;: ")
            title = f"{trimmed} {_tag}"
    print(f"[upload_youtube] title: {title}")

    # --- Duplicate guard: ONE ledger across Shorts / long-form / clips -------
    # The per-pipeline registries hash the generated TEXT, so the same ruling
    # reworded slipped through and the pipelines couldn't see each other. This
    # keys on the normalized RULING and is shared by every publish path, so a
    # clip can't restate its own parent and a re-run can't repost a topic.
    _ruling = ((atom.get("script") or {}).get("hook") or "").strip() or title
    _ledger = None
    try:
        sys.path.insert(0, str(repo_root / "bin" / "core"))
        import content_ledger as _ledger

        _sys_id = str(atom.get("system") or content_profile(atom) or "")
        _dup, _why, _match = _ledger.check(_ruling, str(repo_root), system_id=_sys_id)
        if _dup:
            eprint(f"ERROR: DUPLICATE BLOCKED — {_why}")
            eprint(f"  attempted: {_ruling!r}")
            eprint(f"  existing:  {(_match or {}).get('title')!r} "
                   f"video={(_match or {}).get('video_id')}")
            return 11
    except Exception as exc:
        eprint(f"WARN: content ledger unavailable ({exc}); relying on registry dedup only")
        _ledger = None
    description = (args.description_override or "").strip() or atom.get("youtube_description") or build_description(atom, day)
    privacy = (os.getenv("BIZZAL_YT_PRIVACY") or "private").strip().lower()
    if privacy not in {"private", "unlisted", "public"}:
        privacy = "private"
    category_id = (args.category_id or "").strip() or (os.getenv("BIZZAL_YT_CATEGORY_ID") or "20").strip()  # Gaming

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
            publish_at=(args.publish_at or "").strip(),
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
            **({"tone_lint_violation": (atom.get("diagnostics") or {}).get("tone_lint_violation")} if (atom.get("diagnostics") or {}).get("tone_lint_violation") else {}),
        }
    )
    save_registry(registry_file, registry)
    print(f"[upload_youtube] registry={registry_file} hash={publish_hash[:16]}")

    # Record the ruling so no pipeline can ever republish it (DB + JSON mirror).
    if _ledger is not None:
        try:
            _key = _ledger.record(
                _ruling, str(repo_root),
                system_id=str(atom.get("system") or content_profile(atom)),
                kind=str(atom.get("content_type") or "short"),
                title=title, video_id=vid, day=day,
            )
            print(f"[upload_youtube] ledger recorded key={_key[:16]}")
        except Exception as exc:
            eprint(f"WARN: ledger record failed ({exc}); duplicate risk on re-run")

    # Attach our accurate caption track (best-effort; never fails the publish).
    maybe_upload_captions(youtube, vid, video_path)
    maybe_set_thumbnail(youtube, vid, video_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
