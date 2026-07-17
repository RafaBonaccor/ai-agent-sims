import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from agent_runtime.models import ProjectJobPresetCreate
from agent_runtime.project_gateway import ProjectGateway, ProjectJobCreate
from agent_runtime.storage import RuntimeStore


class ProjectGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        (root / "config").mkdir()
        (root / "integrations" / "demo").mkdir(parents=True)
        (root / "projects" / "demo").mkdir(parents=True)
        (root / "config" / "projects.json").write_text(
            json.dumps(
                {
                    "projects": [
                        {
                            "id": "demo",
                            "name": "Demo",
                            "root": "projects/demo",
                            "integration": "integrations/demo/adapter.json",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (root / "integrations" / "demo" / "adapter.json").write_text(
            json.dumps(
                {
                    "runtime": {"entrypoint": "main.py", "venvCandidates": []},
                    "actions": {
                        "read": {
                            "label": "Read demo",
                            "arguments": ["status"],
                            "parameters": ["query"],
                        },
                        "write": {"arguments": ["submit"], "requiresApproval": True},
                    },
                }
            ),
            encoding="utf-8",
        )

        async def emit(_event):
            return None

        self.store = RuntimeStore(root / "runtime.db")
        self.gateway = ProjectGateway(root, emit, self.store)

    async def asyncTearDown(self):
        await self.gateway.shutdown()
        self.store.close()
        self.temporary_directory.cleanup()

    async def test_rejects_parameters_outside_action_allowlist(self):
        with self.assertRaisesRegex(ValueError, "Unsupported parameters"):
            await self.gateway.create_job(
                ProjectJobCreate(project_id="demo", action="read", parameters={"shell": "whoami"})
            )

    async def test_exposes_human_action_labels(self):
        projects = self.gateway.list_projects()
        self.assertEqual("Read demo", projects[0]["actions"][0]["label"])

    async def test_requires_explicit_approval_for_external_action(self):
        with self.assertRaisesRegex(PermissionError, "requires explicit approval"):
            await self.gateway.create_job(ProjectJobCreate(project_id="demo", action="write"))

    async def test_saves_lists_and_deletes_job_presets(self):
        preset = self.gateway.create_preset(
            ProjectJobPresetCreate(
                name="Daily query",
                project_id="demo",
                action="read",
                parameters={"query": "example"},
            )
        )
        loaded = self.gateway.list_presets("demo")
        self.assertEqual([preset.id], [item.id for item in loaded])
        self.assertEqual("example", loaded[0].parameters["query"])
        self.assertTrue(self.gateway.delete_preset(preset.id))
        self.assertEqual([], self.gateway.list_presets("demo"))

    async def test_preset_uses_action_parameter_allowlist(self):
        with self.assertRaisesRegex(ValueError, "Unsupported parameters"):
            self.gateway.create_preset(
                ProjectJobPresetCreate(
                    name="Unsafe preset",
                    project_id="demo",
                    action="read",
                    parameters={"shell": "whoami"},
                )
            )

    async def test_can_schedule_a_job_for_a_specific_time(self):
        scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=5)
        job = await self.gateway.create_job(
            ProjectJobCreate(
                project_id="demo",
                action="read",
                parameters={"query": "example"},
                schedule_mode="at",
                scheduled_for=scheduled_for,
            )
        )
        self.assertEqual("scheduled", job.state)
        self.assertIsNotNone(job.scheduled_for)
        self.assertGreater(job.scheduled_for, datetime.now(timezone.utc))

    async def test_can_schedule_a_job_with_cron_expression(self):
        job = await self.gateway.create_job(
            ProjectJobCreate(
                project_id="demo",
                action="read",
                parameters={"query": "example"},
                schedule_mode="cron",
                cron_expression="* * * * *",
            )
        )
        self.assertEqual("scheduled", job.state)
        self.assertIsNotNone(job.scheduled_for)
        self.assertEqual("cron", job.schedule_mode.value)

    async def test_weekday_recurring_schedule_finds_next_occurrence(self):
        base = datetime(2026, 7, 9, 9, 30, tzinfo=timezone.utc)
        next_run = self.gateway._next_weekday_occurrence(base, [0, 2, 4])
        self.assertIsNotNone(next_run)
        self.assertEqual(4, next_run.weekday())
        self.assertGreater(next_run, base)

    async def test_daily_recurring_schedule_moves_forward_one_day(self):
        scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=5)
        job = await self.gateway.create_job(
            ProjectJobCreate(
                project_id="demo",
                action="read",
                parameters={"query": "example"},
                schedule_mode="at",
                scheduled_for=scheduled_for,
                repeat_mode="daily",
            )
        )
        self.assertEqual("daily", job.repeat_mode.value)
        self.assertEqual("scheduled", job.state)

    async def test_weekday_repeat_mode_persists_selected_days(self):
        scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=5)
        job = await self.gateway.create_job(
            ProjectJobCreate(
                project_id="demo",
                action="read",
                parameters={"query": "example"},
                schedule_mode="at",
                scheduled_for=scheduled_for,
                repeat_mode="weekdays",
                weekdays=[0, 2, 4],
            )
        )
        self.assertEqual("weekdays", job.repeat_mode.value)
        self.assertEqual([0, 2, 4], job.weekdays)

    def test_macos_local_ui_uses_terminal_launcher(self):
        action = {"risk": "local-ui"}
        with patch("agent_runtime.project_gateway.sys.platform", "darwin"):
            self.assertTrue(self.gateway._should_launch_via_macos_terminal(action))
            command = self.gateway._macos_terminal_command(
                ["/tmp/python", "/tmp/main.py", "gui"],
                Path("/tmp/demo project"),
            )

        self.assertEqual("osascript", command[0])
        self.assertIn("Terminal", " ".join(command))
        self.assertIn("exec /tmp/python /tmp/main.py gui", " ".join(command))
        self.assertIn("cd '/tmp/demo project'", " ".join(command))


if __name__ == "__main__":
    unittest.main()
