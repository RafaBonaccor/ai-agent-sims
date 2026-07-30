import asyncio
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_runtime.error_reporting import (
    RuntimeErrorReporter,
    build_error_report_message,
    recent_project_screenshot_paths,
    send_discord_webhook_message,
)
from agent_runtime.models import DiagnosticsSettings, SystemSettings


class _FakeWebhookResponse:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return b""


class ErrorReportingTests(unittest.TestCase):
    def test_build_error_report_message_contains_core_context(self) -> None:
        message = build_error_report_message(
            "project.job.failed",
            "Browser crashed",
            {"project_id": "main-scraper", "job_id": "job-1", "current_url": "https://www.vinted.it/items/1"},
        )

        self.assertIn("Agent Lab error report", message)
        self.assertIn("project.job.failed", message)
        self.assertIn("Browser crashed", message)
        self.assertIn("main-scraper", message)
        self.assertIn("https://www.vinted.it/items/1", message)

    @patch("agent_runtime.error_reporting.urlopen", return_value=_FakeWebhookResponse())
    def test_send_discord_webhook_message_supports_attachments(self, mocked_urlopen) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            screenshot = Path(temp_dir) / "screenshot.png"
            screenshot.write_bytes(b"fake-image")
            result = send_discord_webhook_message(
                "https://discord.com/api/webhooks/test/token",
                "ciao",
                attachment_paths=[screenshot],
            )

        self.assertTrue(result["ok"])
        self.assertEqual([str(screenshot.resolve())], result["attachments"])
        request = mocked_urlopen.call_args.args[0]
        self.assertIn("multipart/form-data", str(request.get_header("Content-type") or ""))

    def test_recent_project_screenshot_paths_prefers_recent_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recent_dir = root / "error_logs" / "latest"
            old_dir = root / "error_logs" / "old"
            recent_dir.mkdir(parents=True)
            old_dir.mkdir(parents=True)
            old = old_dir / "screenshot.png"
            recent = recent_dir / "screenshot.png"
            old.write_bytes(b"old")
            recent.write_bytes(b"recent")

            paths = recent_project_screenshot_paths(root, max_age_seconds=900, limit=2)

        self.assertTrue(paths)
        self.assertEqual(recent.resolve(), paths[0])

    @patch("agent_runtime.error_reporting.urlopen", return_value=_FakeWebhookResponse())
    def test_runtime_error_reporter_persists_data_url_screenshot(self, _mocked_urlopen) -> None:
        png_bytes = base64.b64encode(b"fake-png").decode("ascii")
        settings = SystemSettings(
            configured=True,
            diagnostics=DiagnosticsSettings(
                discord_error_notifications=True,
                discord_webhook_url="https://discord.com/api/webhooks/test/token",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            reporter = RuntimeErrorReporter(Path(temp_dir), lambda: settings)
            result = asyncio.run(
                reporter.report(
                    source="ui.window.error",
                    message="Broken UI",
                    screenshot_data_url=f"data:image/png;base64,{png_bytes}",
                )
            )
            saved = sorted((Path(temp_dir) / "runtime" / "error_reports").glob("**/*.png"))

        self.assertTrue(result["ok"])
        self.assertTrue(saved)
