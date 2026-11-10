from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_runtime.linkedin_reports import (
    LinkedInReportError, _safe_media_url, archive_linkedin_media,
    archived_media_path, get_linkedin_post, list_linkedin_posts, save_linkedin_rewrite,
)


class LinkedInReportsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        db_path = self.root / "projects" / "main-scraper" / "data" / "linkedin_posts.db"
        db_path.parent.mkdir(parents=True)
        with sqlite3.connect(db_path) as db:
            db.execute("""CREATE TABLE posts (
                post_id TEXT PRIMARY KEY, link TEXT, author TEXT, author_url TEXT,
                text TEXT, published_text TEXT, image_url TEXT,
                first_seen_at TEXT, last_seen_at TEXT, avatar_url TEXT
            )""")
            db.execute("""CREATE TABLE post_observations (
                post_id TEXT, keyword TEXT, observed_at TEXT, reactions INTEGER,
                comments INTEGER, reposts INTEGER, engagement_score INTEGER
            )""")
            db.execute("INSERT INTO posts VALUES (?,?,?,?,?,?,?,?,?,?)", (
                "post-1", "https://www.linkedin.com/feed/", "Author", "", "A useful post", "2d",
                "https://media.licdn.com/dms/image/a.png", "2026-11-10T09:00:00", "2026-11-10T09:00:00", "",
            ))
            db.execute("INSERT INTO post_observations VALUES (?,?,?,?,?,?,?)", (
                "post-1", "feed", "2026-11-10T09:00:00", 1200, 7, 2, 1220,
            ))

    def tearDown(self):
        self.directory.cleanup()

    def test_list_detail_legacy_image_and_rewrite(self):
        rows = list_linkedin_posts(self.root)
        self.assertEqual(rows["total"], 1)
        self.assertEqual(rows["posts"][0]["reactions"], 1200)
        detail = get_linkedin_post(self.root, "post-1")
        self.assertEqual(detail["media"][0]["kind"], "image")
        draft = save_linkedin_rewrite(self.root, "post-1", "My original draft", "Be clear", "test-model")
        self.assertEqual(draft["draft"], get_linkedin_post(self.root, "post-1")["rewrites"][0]["draft"])

    def test_url_allowlist_blocks_private_and_non_https_hosts(self):
        self.assertEqual(_safe_media_url("https://media.licdn.com/dms/image/abc"),
                         "https://media.licdn.com/dms/image/abc")
        for url in ("http://media.licdn.com/x", "https://localhost/x",
                    "https://media.licdn.com.evil.test/x", "https://user@media.licdn.com/x"):
            with self.assertRaises(LinkedInReportError):
                _safe_media_url(url)

    @patch("agent_runtime.linkedin_reports._download_one")
    def test_archive_uses_safe_fallback_and_returns_local_file(self, download):
        def attempt(url, *, kind, destination):
            if url.endswith("a.png"):
                raise LinkedInReportError("expired")
            destination.write_bytes(b"\x89PNG\r\n\x1a\n" + b"sample")
            return "image/png", destination.stat().st_size, "abcd", url

        download.side_effect = attempt
        # get_linkedin_post creates the media schema on first access.
        get_linkedin_post(self.root, "post-1")
        with sqlite3.connect(self.root / "projects" / "main-scraper" / "data" / "linkedin_posts.db") as db:
            db.execute("INSERT INTO post_media VALUES (?,?,?,?,?,?)", (
                "post-1", 0, "image", '["https://media.licdn.com/dms/image/a.png", "https://media.licdn.com/dms/image/b.png"]',
                "", "2026-11-10T09:00:00",
            ))
        result = archive_linkedin_media(self.root, "post-1", 0)
        self.assertEqual(result["mime_type"], "image/png")
        self.assertTrue(archived_media_path(self.root, "post-1", 0, "original").exists())
        self.assertEqual(download.call_count, 2)

    @patch("agent_runtime.linkedin_reports._download_one")
    def test_video_without_source_can_only_archive_poster(self, download):
        get_linkedin_post(self.root, "post-1")
        with sqlite3.connect(self.root / "projects" / "main-scraper" / "data" / "linkedin_posts.db") as db:
            db.execute("INSERT INTO post_media VALUES (?,?,?,?,?,?)", (
                "post-1", 0, "video", "[]", "https://media.licdn.com/dms/image/poster.jpg",
                "2026-11-10T09:00:00",
            ))
        with self.assertRaisesRegex(LinkedInReportError, "No downloadable URL"):
            archive_linkedin_media(self.root, "post-1", 0)
        download.assert_not_called()
        def save_poster(url, *, kind, destination):
            self.assertEqual(kind, "image")
            destination.write_bytes(b"\xff\xd8\xffposter")
            return "image/jpeg", destination.stat().st_size, "poster-hash", url

        download.side_effect = save_poster
        result = archive_linkedin_media(self.root, "post-1", 0, poster=True)
        self.assertEqual(result["variant"], "poster")
        self.assertTrue(archived_media_path(self.root, "post-1", 0, "poster").exists())


if __name__ == "__main__":
    unittest.main()
