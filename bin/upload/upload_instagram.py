#!/usr/bin/env python3
"""
Upload the daily rendered Short to Instagram Reels.

Flow:
  1. Upload MP4 (and optional cover PNG) as GitHub Release assets to get public URLs
  2. POST to Instagram Graph API to create a Reels container (with cover_url if available)
  3. Poll container until status_code == FINISHED (up to ~4 min)
  4. POST to media_publish
  5. Delete the GitHub Release (clean up temp hosting)
  6. Append result to publish registry

Secrets required (GitHub Actions env / local env):
  BIZZAL_IG_ACCESS_TOKEN  — long-lived Instagram Graph API token
  BIZZAL_IG_USER_ID       — numeric Instagram Business/Creator account user ID
  GITHUB_TOKEN            — already available in Actions; needed for temp Release hosting
  GITHUB_REPOSITORY       — e.g. "bizzal70/Bizzal-Games-YT-PUB" (set automatically in Actions)
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

GRAPH_BASE = "https://graph.instagram.com/v20.0"
GITHUB_API = "https://api.github.com"


def eprint(msg: str):
    print(msg, file=sys.stderr)


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


def load_atom(repo_root: Path, day: str) -> dict:
    validated_dir_raw = (os.getenv("BIZZAL_ATOM_VALIDATED_DIR") or "data/atoms/validated").strip()
    validated_dir = Path(validated_dir_raw).expanduser()
    if not validated_dir.is_absolute():
        validated_dir = repo_root / validated_dir
    atom_path = validated_dir / f"{day}.json"
    if not atom_path.is_file():
        raise FileNotFoundError(f"validated atom missing: {atom_path}")
    return json.loads(atom_path.read_text(encoding="utf-8"))


def default_video_path_for_day(repo_root: Path, day: str) -> Path:
    by_day_dir_raw = (os.getenv("BIZZAL_RENDERS_BY_DAY_DIR") or "data/renders/by_day").strip()
    by_day_dir = Path(by_day_dir_raw).expanduser()
    if not by_day_dir.is_absolute():
        by_day_dir = repo_root / by_day_dir
    day_video = by_day_dir / f"{day}.mp4"
    if day_video.is_file():
        return day_video
    latest_raw = (os.getenv("BIZZAL_LATEST_VIDEO_PATH") or "data/renders/latest/latest.mp4").strip()
    latest_path = Path(latest_raw).expanduser()
    if not latest_path.is_absolute():
        latest_path = repo_root / latest_path
    return latest_path


def cover_image_path_for_day(repo_root: Path, day: str) -> Path | None:
    """Return the bg PNG for the day if it exists, else None."""
    by_day_dir_raw = (os.getenv("BIZZAL_RENDERS_BY_DAY_DIR") or "data/renders/by_day").strip()
    by_day_dir = Path(by_day_dir_raw).expanduser()
    if not by_day_dir.is_absolute():
        by_day_dir = repo_root / by_day_dir
    cover = by_day_dir / f"{day}.bg.png"
    return cover if cover.is_file() else None


def ig_registry_path(repo_root: Path) -> Path:
    val = (os.getenv("BIZZAL_IG_REGISTRY") or "data/state/published_registry_instagram.json").strip()
    p = Path(val).expanduser()
    if not p.is_absolute():
        p = repo_root / p
    return p


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


def build_caption(atom: dict, day: str) -> str:
    script = atom.get("script") or {}
    hook = (script.get("hook") or "").strip()
    body = (script.get("body") or "").strip()
    cta = (script.get("cta") or "").strip()
    fact = atom.get("fact") or {}
    name = (fact.get("name") or "").strip()
    profile = content_profile(atom)
    if profile == "shadowdark":
        tags = "#shadowdark #osr #ttrpg #rpg #shorts #reels"
    else:
        tags = "#dnd #dnd5e #ttrpg #rpg #shorts #reels"
    parts = []
    if name:
        parts.append(name)
    if hook:
        parts.append(hook)
    if body:
        parts.append(body)
    if cta:
        parts.append(cta)
    parts.append(tags)
    caption = "\n\n".join(p for p in parts if p)
    return caption[:2200]  # Instagram caption limit


# ---------------------------------------------------------------------------
# GitHub Releases — temp video hosting
# ---------------------------------------------------------------------------

def gh_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def create_temp_release(repo: str, token: str, day: str) -> dict:
    tag = f"temp-ig-{day}-{int(time.time())}"
    r = requests.post(
        f"{GITHUB_API}/repos/{repo}/releases",
        headers=gh_headers(token),
        json={
            "tag_name": tag,
            "name": f"Temp IG hosting {day}",
            "body": "Temporary asset for Instagram Reels upload. Auto-deleted after publish.",
            "draft": False,
            "prerelease": True,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def upload_release_asset(upload_url: str, file_path: Path, token: str, content_type: str = "video/mp4") -> str:
    """Upload a file to GitHub Release assets; returns the browser_download_url."""
    base_url = upload_url.split("{")[0]
    url = f"{base_url}?name={file_path.name}"
    with file_path.open("rb") as f:
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": content_type,
            },
            data=f,
            timeout=300,
        )
    r.raise_for_status()
    return r.json()["browser_download_url"]


def delete_release(repo: str, release_id: int, token: str):
    """Delete the temp GitHub Release (and its assets) after Instagram publish."""
    try:
        r = requests.delete(
            f"{GITHUB_API}/repos/{repo}/releases/{release_id}",
            headers=gh_headers(token),
            timeout=30,
        )
        r.raise_for_status()
        print(f"[upload_instagram] deleted temp release id={release_id}")
    except Exception as exc:
        eprint(f"WARNING: failed to delete temp release {release_id}: {exc}")


# ---------------------------------------------------------------------------
# Instagram Graph API
# ---------------------------------------------------------------------------


def ig_check_token(access_token: str) -> None:
    """Warn if the Instagram token is expiring within 7 days."""
    try:
        r = requests.get(
            f"{GRAPH_BASE}/me",
            params={"fields": "id,username"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        if not r.ok:
            eprint(f"WARNING: Instagram token health check failed {r.status_code}: {r.text}")
        else:
            print(f"[upload_instagram] token ok, user={r.json().get('username')}")
    except Exception as exc:
        eprint(f"WARNING: Instagram token health check error: {exc}")

def ig_create_reels_container(
    ig_user_id: str,
    access_token: str,
    video_url: str,
    caption: str,
    cover_url: str | None = None,
) -> str:
    """Returns container_id."""
    params = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
    }
    if cover_url:
        params["cover_url"] = cover_url
    r = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media",
        params=params,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"Instagram create container failed {r.status_code}: {r.text}")
    return r.json()["id"]


def ig_poll_container(container_id: str, access_token: str, timeout_sec: int = 300) -> str:
    """Poll until status_code == FINISHED. Returns container_id on success."""
    deadline = time.time() + timeout_sec
    interval = 15
    while time.time() < deadline:
        r = requests.get(
            f"{GRAPH_BASE}/{container_id}",
            params={"fields": "status_code,status"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        status = data.get("status_code") or data.get("status") or ""
        print(f"[upload_instagram] container {container_id} status={status}")
        if status == "FINISHED":
            return container_id
        if status in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"Instagram container failed with status={status}: {data}")
        time.sleep(interval)
    raise TimeoutError(f"Instagram container {container_id} did not finish within {timeout_sec}s")


def ig_publish_container(ig_user_id: str, access_token: str, container_id: str) -> str:
    """Returns the Instagram post/media ID."""
    r = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media_publish",
        params={"creation_id": container_id},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"Instagram publish failed {r.status_code}: {r.text}")
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Upload latest rendered short to Instagram Reels")
    parser.add_argument("--day", default=os.getenv("BIZZAL_DAY", ""), help="Day YYYY-MM-DD")
    parser.add_argument("--video", default="", help="Video path override")
    args = parser.parse_args()

    ig_access_token = (os.getenv("BIZZAL_IG_ACCESS_TOKEN") or "").strip()
    ig_user_id = (os.getenv("BIZZAL_IG_USER_ID") or "").strip()
    github_token = (os.getenv("GITHUB_TOKEN") or "").strip()
    github_repo = (os.getenv("GITHUB_REPOSITORY") or "").strip()

    if not ig_access_token:
        eprint("ERROR: BIZZAL_IG_ACCESS_TOKEN is not set")
        return 1
    if not ig_user_id:
        eprint("ERROR: BIZZAL_IG_USER_ID is not set")
        return 1
    if not github_token:
        eprint("ERROR: GITHUB_TOKEN is not set")
        return 1
    if not github_repo:
        eprint("ERROR: GITHUB_REPOSITORY is not set (e.g. bizzal70/Bizzal-Games-YT-PUB)")
        return 1

    ig_check_token(ig_access_token)

    repo_root = Path(__file__).resolve().parents[2]

    day = args.day.strip()
    if not day:
        day = datetime.now().strftime("%Y-%m-%d")

    try:
        video_path = Path(args.video).expanduser() if args.video else default_video_path_for_day(repo_root, day)
    except FileNotFoundError as exc:
        eprint(f"ERROR: {exc}")
        return 2
    if not video_path.is_file():
        eprint(f"ERROR: video not found: {video_path}")
        return 2

    try:
        atom = load_atom(repo_root, day)
    except Exception as exc:
        eprint(f"ERROR: unable to load atom for day {day}: {exc}")
        return 3

    cover_path = cover_image_path_for_day(repo_root, day)
    if cover_path:
        print(f"[upload_instagram] cover image found: {cover_path.name}")
    else:
        print("[upload_instagram] no cover image found; Instagram will auto-select a frame")

    video_sha = sha256_file(video_path)
    content_id = str(((atom.get("content") or {}).get("content_id") or "")).strip()

    # Dedup check against Instagram registry
    registry_file = ig_registry_path(repo_root)
    registry = load_registry(registry_file)
    for item in registry.get("items") or []:
        if isinstance(item, dict) and item.get("content_id") == content_id and content_id:
            prior_id = item.get("instagram_post_id") or "(unknown)"
            eprint(f"ERROR: duplicate publish blocked. content_id={content_id} prior_post={prior_id}")
            return 6

    caption = build_caption(atom, day)
    print(f"[upload_instagram] caption preview: {caption[:120]}...")

    # Step 1: upload to GitHub Releases for a public URL
    print(f"[upload_instagram] creating temp GitHub Release in {github_repo}")
    release = create_temp_release(github_repo, github_token, day)
    release_id = release["id"]
    upload_url = release["upload_url"]

    video_url = None
    cover_url = None
    try:
        print(f"[upload_instagram] uploading {video_path.name} ({video_path.stat().st_size // 1024}KB)")
        video_url = upload_release_asset(upload_url, video_path, github_token, "video/mp4")
        print(f"[upload_instagram] temp video url={video_url}")

        if cover_path:
            print(f"[upload_instagram] uploading cover {cover_path.name} ({cover_path.stat().st_size // 1024}KB)")
            cover_url = upload_release_asset(upload_url, cover_path, github_token, "image/png")
            print(f"[upload_instagram] temp cover url={cover_url}")

        # Step 2: create Instagram Reels container
        print("[upload_instagram] creating Reels container")
        container_id = ig_create_reels_container(ig_user_id, ig_access_token, video_url, caption, cover_url)
        print(f"[upload_instagram] container_id={container_id}")

        # Step 3: poll until FINISHED
        ig_poll_container(container_id, ig_access_token)

        # Step 4: publish
        print("[upload_instagram] publishing")
        post_id = ig_publish_container(ig_user_id, ig_access_token, container_id)
        print(f"[upload_instagram] published post_id={post_id}")

    except Exception as exc:
        eprint(f"ERROR: Instagram publish failed: {exc}")
        return 4
    finally:
        # Step 5: always clean up temp release
        if video_url:
            delete_release(github_repo, release_id, github_token)

    # Step 6: update registry
    fact = atom.get("fact") or {}
    registry["items"].append({
        "published_utc": utc_now(),
        "day": day,
        "content_id": content_id,
        "instagram_post_id": post_id,
        "instagram_user_id": ig_user_id,
        "video_sha256": video_sha,
        "video_path": str(video_path),
        "fact_name": (fact.get("name") or "").strip(),
        "category": atom.get("category") or "",
        "hook": ((atom.get("script") or {}).get("hook") or "").strip(),
        "body": ((atom.get("script") or {}).get("body") or "").strip(),
        "cta": ((atom.get("script") or {}).get("cta") or "").strip(),
    })
    save_registry(registry_file, registry)
    print(f"[upload_instagram] registry={registry_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
