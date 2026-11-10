"""Read-only LinkedIn report data and explicitly requested media archives."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx


class LinkedInReportError(ValueError):
    pass


def _db_path(root: Path) -> Path:
    return root / "projects" / "main-scraper" / "data" / "linkedin_posts.db"


def _connect(root: Path) -> sqlite3.Connection:
    db = sqlite3.connect(_db_path(root), timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=30000")
    return db


def _ensure_tables(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS post_media (
        post_id TEXT NOT NULL, media_index INTEGER NOT NULL, kind TEXT NOT NULL,
        urls_json TEXT NOT NULL DEFAULT '[]', poster_url TEXT NOT NULL DEFAULT '',
        detected_at TEXT NOT NULL, PRIMARY KEY(post_id, media_index)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS media_archive (
        post_id TEXT NOT NULL, media_index INTEGER NOT NULL, variant TEXT NOT NULL,
        relative_path TEXT NOT NULL, source_url TEXT NOT NULL, mime_type TEXT NOT NULL,
        byte_size INTEGER NOT NULL, sha256 TEXT NOT NULL, archived_at TEXT NOT NULL,
        PRIMARY KEY(post_id, media_index, variant)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS post_rewrites (
        rewrite_id INTEGER PRIMARY KEY AUTOINCREMENT, post_id TEXT NOT NULL,
        draft TEXT NOT NULL, instruction TEXT NOT NULL, model TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")


def list_linkedin_posts(root: Path, *, limit: int = 500, search: str = "") -> dict:
    if not _db_path(root).exists():
        return {"available": False, "posts": [], "total": 0}
    with _connect(root) as db:
        _ensure_tables(db)
        term = f"%{search.strip()[:100]}%"
        rows = db.execute("""SELECT p.post_id,p.link,p.author,p.text,p.published_text,
            p.image_url,p.first_seen_at,p.last_seen_at,
            COALESCE(MAX(o.reactions),0) reactions, COALESCE(MAX(o.comments),0) comments,
            COALESCE(MAX(o.reposts),0) reposts,
            (SELECT COUNT(*) FROM post_media m WHERE m.post_id=p.post_id AND m.kind='image') image_count,
            (SELECT COUNT(*) FROM post_media m WHERE m.post_id=p.post_id AND m.kind='video') video_count,
            (SELECT COUNT(*) FROM media_archive a WHERE a.post_id=p.post_id) archived_count
            FROM posts p LEFT JOIN post_observations o ON o.post_id=p.post_id
            WHERE p.text LIKE ? OR p.author LIKE ?
            GROUP BY p.post_id ORDER BY reactions DESC,p.last_seen_at DESC LIMIT ?""",
            (term, term, max(1, min(limit, 2000)))).fetchall()
        total = db.execute("SELECT COUNT(*) FROM posts WHERE text LIKE ? OR author LIKE ?", (term, term)).fetchone()[0]
    return {"available": True, "total": total, "posts": [dict(row) for row in rows]}


def _post_media(db: sqlite3.Connection, post: sqlite3.Row) -> list[dict]:
    media = []
    for row in db.execute("SELECT * FROM post_media WHERE post_id=? ORDER BY media_index", (post["post_id"],)):
        try:
            urls = json.loads(row["urls_json"])
        except (TypeError, json.JSONDecodeError):
            urls = []
        media.append({"index": row["media_index"], "kind": row["kind"],
                      "urls": urls if isinstance(urls, list) else [],
                      "poster_url": row["poster_url"]})
    image = str(post["image_url"] or "").strip()
    if image and not any(item["kind"] == "image" and image in item["urls"] for item in media):
        media.append({"index": max((item["index"] for item in media), default=-1) + 1,
                      "kind": "image", "urls": [image], "poster_url": ""})
    for item in media:
        item["archive"] = [dict(row) for row in db.execute(
            "SELECT variant,relative_path,mime_type,byte_size,archived_at FROM media_archive WHERE post_id=? AND media_index=?",
            (post["post_id"], item["index"]),
        )]
    return media


def get_linkedin_post(root: Path, post_id: str) -> dict:
    with _connect(root) as db:
        _ensure_tables(db)
        post = db.execute("SELECT * FROM posts WHERE post_id=?", (post_id,)).fetchone()
        if post is None:
            raise LinkedInReportError("Post not found")
        observations = [dict(row) for row in db.execute(
            "SELECT observed_at,reactions,comments,reposts FROM post_observations WHERE post_id=? ORDER BY observed_at DESC LIMIT 30",
            (post_id,),
        )]
        rewrites = [dict(row) for row in db.execute(
            "SELECT rewrite_id,draft,instruction,model,created_at FROM post_rewrites WHERE post_id=? ORDER BY rewrite_id DESC LIMIT 10",
            (post_id,),
        )]
        return {**dict(post), "media": _post_media(db, post), "observations": observations,
                "rewrites": rewrites}


def _safe_media_url(value: str) -> str:
    url = urlparse(value)
    host = (url.hostname or "").lower().rstrip(".")
    try:
        port = url.port
    except ValueError as exc:
        raise LinkedInReportError("Invalid media URL port") from exc
    if url.scheme != "https" or url.username or url.password or port not in (None, 443):
        raise LinkedInReportError("Only HTTPS media URLs are permitted")
    if not (host == "licdn.com" or host.endswith(".licdn.com")):
        raise LinkedInReportError("Media host is not permitted")
    return value


def _media_candidates(media: dict, *, poster: bool) -> list[str]:
    if poster:
        return [media["poster_url"]] if media.get("poster_url") else []
    urls = [str(url) for url in media.get("urls", [])]
    return [url for url in urls if url.startswith("https://")]


def _download_one(url: str, *, kind: str, destination: Path) -> tuple[str, int, str, str]:
    limit = 25 * 1024 * 1024 if kind == "image" else 512 * 1024 * 1024
    current = _safe_media_url(url)
    with httpx.Client(timeout=httpx.Timeout(25, connect=8), follow_redirects=False) as client:
        for _ in range(4):
            with client.stream("GET", current, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/*,video/*"}) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    current = _safe_media_url(urljoin(current, response.headers.get("location", "")))
                    continue
                response.raise_for_status()
                mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if not mime.startswith(kind + "/"):
                    raise LinkedInReportError(f"Expected {kind} content, received {mime or 'unknown'}")
                length = int(response.headers.get("content-length", "0") or 0)
                if length > limit:
                    raise LinkedInReportError(f"{kind} exceeds the size limit")
                digest = hashlib.sha256()
                size = 0
                first = b""
                with destination.open("wb") as output:
                    for chunk in response.iter_bytes(256 * 1024):
                        if not chunk:
                            continue
                        size += len(chunk)
                        if size > limit:
                            raise LinkedInReportError(f"{kind} exceeds the size limit")
                        if len(first) < 16:
                            first = (first + chunk)[:16]
                        digest.update(chunk)
                        output.write(chunk)
                if not size or (kind == "image" and not (
                    first.startswith((b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"RIFF")) or first[4:12] in {b"ftypavif", b"ftypheic"}
                )):
                    raise LinkedInReportError("Downloaded bytes are not a supported image")
                if kind == "video" and b"ftyp" not in first[:12] and not first.startswith(b"\x1a\x45\xdf\xa3"):
                    raise LinkedInReportError("Downloaded bytes are not an MP4/WebM video")
                return mime, size, digest.hexdigest(), current
    raise LinkedInReportError("Too many media redirects")


def archive_linkedin_media(root: Path, post_id: str, media_index: int, *, poster: bool = False) -> dict:
    detail = get_linkedin_post(root, post_id)
    media = next((item for item in detail["media"] if item["index"] == media_index), None)
    if media is None:
        raise LinkedInReportError("Media not found")
    kind = "image" if poster else media["kind"]
    urls = _media_candidates(media, poster=poster)
    if not urls:
        raise LinkedInReportError("No downloadable URL is available; this may be a temporary video stream")
    archive_root = root / "data" / "linkedin_media"
    archive_root.mkdir(parents=True, exist_ok=True)
    post_hash = hashlib.sha256(post_id.encode()).hexdigest()[:24]
    variant = "poster" if poster else "original"
    failures = []
    for url in urls:
        temporary = archive_root / f".{post_hash}_{media_index}_{variant}_{uuid.uuid4().hex}.partial"
        try:
            mime, size, digest, final_url = _download_one(url, kind=kind, destination=temporary)
            extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                         "image/gif": ".gif", "image/avif": ".avif", "video/mp4": ".mp4",
                         "video/webm": ".webm"}.get(mime)
            if extension is None:
                raise LinkedInReportError(f"Unsupported media type: {mime}")
            name = f"{post_hash}_{media_index}_{variant}{extension}"
            target = archive_root / name
            os.replace(temporary, target)
            relative = str(target.relative_to(root))
            with _connect(root) as db:
                _ensure_tables(db)
                db.execute("""INSERT INTO media_archive VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(post_id,media_index,variant) DO UPDATE SET
                    relative_path=excluded.relative_path,source_url=excluded.source_url,
                    mime_type=excluded.mime_type,byte_size=excluded.byte_size,
                    sha256=excluded.sha256,archived_at=excluded.archived_at""",
                    (post_id, media_index, variant, relative, final_url, mime, size, digest,
                     datetime.now().isoformat(timespec="seconds")))
            return {"post_id": post_id, "media_index": media_index, "variant": variant,
                    "relative_path": relative, "mime_type": mime, "byte_size": size,
                    "sha256": digest}
        except (httpx.HTTPError, OSError, LinkedInReportError, ValueError) as exc:
            # CDN URLs may contain temporary tokens; never echo them into the UI.
            failures.append(str(exc) if isinstance(exc, LinkedInReportError) else type(exc).__name__)
        finally:
            temporary.unlink(missing_ok=True)
    raise LinkedInReportError("Download unavailable after safe fallbacks: " + "; ".join(failures[:3]))


def archived_media_path(root: Path, post_id: str, media_index: int, variant: str) -> Path:
    if variant not in {"original", "poster"}:
        raise LinkedInReportError("Invalid media variant")
    with _connect(root) as db:
        _ensure_tables(db)
        row = db.execute("SELECT relative_path FROM media_archive WHERE post_id=? AND media_index=? AND variant=?",
                         (post_id, media_index, variant)).fetchone()
    if row is None:
        raise LinkedInReportError("Media has not been archived")
    root_path = (root / "data" / "linkedin_media").resolve()
    path = (root / row["relative_path"]).resolve()
    if root_path not in path.parents or not path.is_file():
        raise LinkedInReportError("Archived media is unavailable")
    return path


def save_linkedin_rewrite(root: Path, post_id: str, draft: str, instruction: str, model: str) -> dict:
    if not draft.strip():
        raise LinkedInReportError("The generated draft is empty")
    with _connect(root) as db:
        _ensure_tables(db)
        if not db.execute("SELECT 1 FROM posts WHERE post_id=?", (post_id,)).fetchone():
            raise LinkedInReportError("Post not found")
        now = datetime.now().isoformat(timespec="seconds")
        cursor = db.execute("INSERT INTO post_rewrites (post_id,draft,instruction,model,created_at) VALUES (?,?,?,?,?)",
                            (post_id, draft, instruction, model, now))
        return {"rewrite_id": cursor.lastrowid, "post_id": post_id, "draft": draft,
                "instruction": instruction, "model": model, "created_at": now}
