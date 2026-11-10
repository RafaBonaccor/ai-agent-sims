"""Reviewed LinkedIn drafts and single-shot publication via copied Chrome profile."""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from .linkedin_reports import (
    LinkedInReportError, archive_linkedin_media, archived_media_path, get_linkedin_post,
)


class LinkedInPublishError(ValueError):
    pass


@contextmanager
def _connect(root: Path):
    path = root / "data" / "linkedin_publisher.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("""CREATE TABLE IF NOT EXISTS drafts (
            draft_id INTEGER PRIMARY KEY AUTOINCREMENT,
            body TEXT NOT NULL, source_post_id TEXT NOT NULL DEFAULT '',
            attachment_path TEXT NOT NULL DEFAULT '', attachment_name TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'draft', post_url TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        columns = {row[1] for row in db.execute("PRAGMA table_info(drafts)")}
        if "attachment_path" not in columns:
            db.execute("ALTER TABLE drafts ADD COLUMN attachment_path TEXT NOT NULL DEFAULT ''")
        if "attachment_name" not in columns:
            db.execute("ALTER TABLE drafts ADD COLUMN attachment_name TEXT NOT NULL DEFAULT ''")
        stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(timespec="seconds")
        db.execute("""UPDATE drafts SET state='unknown',
            error='Publisher interrupted; check LinkedIn before creating another post', updated_at=?
            WHERE state='submitting' AND updated_at<?""", (_now(), stale))
        db.commit()
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def publisher_status(root: Path) -> dict:
    with _connect(root) as db:
        count = db.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
    scraper = root / "projects" / "main-scraper"
    python = scraper / ".venv" / "bin" / "python"
    return {"mode": "chrome_normale", "ready": python.is_file(), "draft_count": count,
            "browser_profile": "Chrome standard (copia separata)",
            "note": "Login verificato al momento della pubblicazione; nessun post inviato automaticamente."}


def create_draft(root: Path, body: str, source_post_id: str = "", attachment_path: str = "") -> dict:
    body = body.strip()
    if not body or len(body) > 3000:
        raise LinkedInPublishError("Draft must contain 1–3000 characters")
    now = _now()
    with _connect(root) as db:
        safe_attachment = ""
        attachment_name = ""
        if attachment_path:
            allowed = (root / "data" / "linkedin_media").resolve()
            candidate = Path(attachment_path).resolve()
            if allowed not in candidate.parents or not candidate.is_file():
                raise LinkedInPublishError("Attached image is not in the local LinkedIn media archive")
            if candidate.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}:
                raise LinkedInPublishError("Only archived images can be attached")
            safe_attachment = str(candidate)
            attachment_name = candidate.name
        cursor = db.execute("INSERT INTO drafts (body,source_post_id,attachment_path,attachment_name,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                            (body, source_post_id[:200], safe_attachment, attachment_name, now, now))
        return _public_draft(db.execute("SELECT * FROM drafts WHERE draft_id=?", (cursor.lastrowid,)).fetchone())


def _public_draft(row: sqlite3.Row) -> dict:
    result = dict(row)
    path = result.pop("attachment_path", "")
    result["has_attachment"] = bool(path)
    return result


def attach_source_image_to_draft(root: Path, draft_id: int) -> dict:
    with _connect(root) as db:
        row = db.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
        if row is None or row["state"] != "draft":
            raise LinkedInPublishError("Draft not found or is no longer editable")
        if not row["source_post_id"]:
            raise LinkedInPublishError("This draft has no source post")
        existing_path = str(row["attachment_path"] or "")
        source_post_id = row["source_post_id"]
    if existing_path and Path(existing_path).is_file():
        with _connect(root) as db:
            return _public_draft(db.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone())

    post = get_linkedin_post(root, source_post_id)
    media = next((item for item in post.get("media", []) if item.get("kind") == "image"), None)
    if media is None:
        raise LinkedInPublishError("No source image was detected for this post")
    try:
        image_path = archived_media_path(root, source_post_id, media["index"], "original")
    except LinkedInReportError:
        archive_linkedin_media(root, source_post_id, media["index"])
        image_path = archived_media_path(root, source_post_id, media["index"], "original")

    allowed = (root / "data" / "linkedin_media").resolve()
    image_path = image_path.resolve()
    if allowed not in image_path.parents or not image_path.is_file() or image_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}:
        raise LinkedInPublishError("Archived source image is unavailable or invalid")
    with _connect(root) as db:
        db.execute("UPDATE drafts SET attachment_path=?,attachment_name=?,updated_at=? WHERE draft_id=? AND state='draft' AND attachment_path=''",
                   (str(image_path), image_path.name, _now(), draft_id))
        row = db.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
        return _public_draft(row)


def draft_attachment_path(root: Path, draft_id: int) -> Path:
    with _connect(root) as db:
        row = db.execute("SELECT attachment_path FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
    if row is None or not row["attachment_path"]:
        raise LinkedInPublishError("Draft image is not available")
    allowed = (root / "data" / "linkedin_media").resolve()
    path = Path(row["attachment_path"]).resolve()
    if allowed not in path.parents or not path.is_file():
        raise LinkedInPublishError("Draft image is not available")
    return path


def list_drafts(root: Path) -> list[dict]:
    with _connect(root) as db:
        return [_public_draft(row) for row in db.execute("SELECT * FROM drafts ORDER BY draft_id DESC LIMIT 200")]


def update_draft(root: Path, draft_id: int, body: str) -> dict:
    body = body.strip()
    if not body or len(body) > 3000:
        raise LinkedInPublishError("Draft must contain 1–3000 characters")
    with _connect(root) as db:
        updated = db.execute("UPDATE drafts SET body=?,updated_at=?,error='' WHERE draft_id=? AND state='draft'",
                             (body, _now(), draft_id))
        if updated.rowcount != 1:
            raise LinkedInPublishError("Draft not found or already submitted")
        return _public_draft(db.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone())


def _run_browser_publisher(root: Path, body: str, attachment_path: str = "") -> dict:
    scraper = root / "projects" / "main-scraper"
    python = scraper / ".venv" / "bin" / "python"
    if not python.is_file():
        raise LinkedInPublishError("Main Scraper Python environment is unavailable")
    try:
        process = subprocess.Popen(
            [str(python), "-m", "scraper_app.sources.linkedin_publish"], cwd=str(scraper),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
    except OSError as exc:
        return {"state": "failed", "clicked": False, "error": f"Could not start browser: {type(exc).__name__}"}
    try:
        stdout, stderr = process.communicate(json.dumps({"body": body, "attachment_path": attachment_path, "browser_mode": "chrome_normale",
                                                         "browser_profile_directory": "Default"}), timeout=180)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise LinkedInPublishError("Publication timed out; outcome unknown. Check LinkedIn before trying again") from exc
    marker = "LINKEDIN_PUBLISH_RESULT="
    lines = [line[len(marker):] for line in stdout.splitlines() if line.startswith(marker)]
    if not lines:
        raise LinkedInPublishError("Browser publisher stopped without a result; check LinkedIn before trying again")
    try:
        result = json.loads(lines[-1])
    except ValueError as exc:
        raise LinkedInPublishError("Browser publisher returned an invalid result") from exc
    return result if isinstance(result, dict) else {"state": "unknown", "error": "Invalid browser result"}


def publish_draft(root: Path, draft_id: int, expected_body: str) -> dict:
    if not (root / "projects" / "main-scraper" / ".venv" / "bin" / "python").is_file():
        raise LinkedInPublishError("Main Scraper Python environment is unavailable")
    with _connect(root) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
        if row is None or row["state"] != "draft":
            raise LinkedInPublishError("Draft not found or already submitted")
        if row["body"] != expected_body:
            raise LinkedInPublishError("Draft changed; review it again before publishing")
        db.execute("UPDATE drafts SET state='submitting',updated_at=? WHERE draft_id=?", (_now(), draft_id))
        body = row["body"]
        attachment_path = row["attachment_path"]
    try:
        result = _run_browser_publisher(root, body, attachment_path)
    except LinkedInPublishError as exc:
        result = {"state": "unknown", "error": str(exc)}
    state = str(result.get("state") or "unknown")
    if state not in {"published", "failed", "unknown"}:
        state = "unknown"
    # A pre-click failure may be edited and retried. After a click, never retry automatically.
    stored_state = "draft" if state == "failed" and not result.get("clicked") else state
    error = str(result.get("error") or "")[:500]
    post_url = str(result.get("post_url") or "")[:1000]
    parsed_url = urlparse(post_url)
    if parsed_url.scheme != "https" or parsed_url.hostname not in {"www.linkedin.com", "linkedin.com"} or not parsed_url.path.startswith("/feed/update/"):
        post_url = ""
    with _connect(root) as db:
        db.execute("UPDATE drafts SET state=?,post_url=?,error=?,updated_at=? WHERE draft_id=? AND state='submitting'",
                   (stored_state, post_url, error, _now(), draft_id))
        return _public_draft(db.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone())
