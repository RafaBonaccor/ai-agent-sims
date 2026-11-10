from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_runtime.server import app

from agent_runtime.linkedin_publisher import (
    LinkedInPublishError, attach_source_image_to_draft, create_draft, draft_attachment_path,
    list_drafts, publish_draft, update_draft,
)
from agent_runtime.linkedin_reports import LinkedInReportError


class LinkedInPublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        python = self.root / "projects" / "main-scraper" / ".venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_bytes(b"test")

    def tearDown(self):
        self.temp.cleanup()

    @patch("agent_runtime.linkedin_publisher._run_browser_publisher")
    def test_confirmed_draft_publishes_once(self, run):
        draft = create_draft(self.root, "An original thought", "source-1")
        run.return_value = {"state": "published", "clicked": True,
                            "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:123/"}
        result = publish_draft(self.root, draft["draft_id"], "An original thought")
        self.assertEqual(result["state"], "published")
        self.assertEqual(run.call_count, 1)
        with self.assertRaises(LinkedInPublishError):
            publish_draft(self.root, draft["draft_id"], "An original thought")
        self.assertEqual(run.call_count, 1)

    @patch("agent_runtime.linkedin_publisher._run_browser_publisher")
    def test_changed_draft_cannot_be_published_without_review(self, run):
        draft = create_draft(self.root, "First version")
        update_draft(self.root, draft["draft_id"], "Final version")
        with self.assertRaisesRegex(LinkedInPublishError, "changed"):
            publish_draft(self.root, draft["draft_id"], "First version")
        run.assert_not_called()

    @patch("agent_runtime.linkedin_publisher._run_browser_publisher")
    def test_uncertain_outcome_is_locked_against_duplicate_posts(self, run):
        draft = create_draft(self.root, "A useful post")
        run.return_value = {"state": "unknown", "clicked": True, "error": "No confirmation"}
        result = publish_draft(self.root, draft["draft_id"], "A useful post")
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(list_drafts(self.root)[0]["state"], "unknown")
        with self.assertRaises(LinkedInPublishError):
            publish_draft(self.root, draft["draft_id"], "A useful post")

    @patch("agent_runtime.linkedin_publisher._run_browser_publisher")
    def test_preclick_failure_keeps_draft_editable(self, run):
        draft = create_draft(self.root, "A useful post")
        run.return_value = {"state": "failed", "clicked": False, "error": "Login missing"}
        result = publish_draft(self.root, draft["draft_id"], "A useful post")
        self.assertEqual(result["state"], "draft")
        self.assertIn("Login", result["error"])

    def test_publish_route_requires_explicit_confirmation_header(self):
        draft = create_draft(self.root, "A useful post")
        with patch("agent_runtime.server.PROJECT_ROOT", self.root):
            response = TestClient(app).post(
                f"/api/linkedin/publisher/drafts/{draft['draft_id']}/publish",
                json={"expected_body": "A useful post"},
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(list_drafts(self.root)[0]["state"], "draft")

    def test_existing_source_draft_can_restore_and_preview_original_image(self):
        draft = create_draft(self.root, "Rewritten post", "source-card-1")
        image = self.root / "data" / "linkedin_media" / "source.jpg"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"image")
        with patch("agent_runtime.linkedin_publisher.get_linkedin_post", return_value={
                "media": [{"kind": "image", "index": 0}]}), \
             patch("agent_runtime.linkedin_publisher.archived_media_path",
                   side_effect=[LinkedInReportError("not archived"), image]), \
             patch("agent_runtime.linkedin_publisher.archive_linkedin_media") as archive:
            updated = attach_source_image_to_draft(self.root, draft["draft_id"])
        self.assertTrue(updated["has_attachment"])
        self.assertEqual(updated["attachment_name"], "source.jpg")
        archive.assert_called_once_with(self.root, "source-card-1", 0)
        self.assertEqual(draft_attachment_path(self.root, draft["draft_id"]), image.resolve())
