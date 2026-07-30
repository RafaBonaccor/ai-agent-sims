import json
import tempfile
import unittest
import asyncio
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from agent_runtime.models import AgentChatMessage
from agent_runtime.models import ProjectJobPresetCreate
from agent_runtime.project_gateway import ProjectGateway, ProjectJob, ProjectJobCreate
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

    async def test_supports_object_parameter_definitions_and_ui_defaults(self):
        (Path(self.temporary_directory.name) / "projects" / "demo" / "data").mkdir(parents=True, exist_ok=True)
        (Path(self.temporary_directory.name) / "projects" / "demo" / "data" / "ui_settings.json").write_text(
            json.dumps({"demo_query": "saved value"}),
            encoding="utf-8",
        )
        (Path(self.temporary_directory.name) / "integrations" / "demo" / "adapter.json").write_text(
            json.dumps(
                {
                    "runtime": {"entrypoint": "main.py", "venvCandidates": []},
                    "actions": {
                        "read": {
                            "label": "Read demo",
                            "arguments": ["status"],
                            "parameters": [
                                {
                                    "id": "query",
                                    "label": "Query",
                                    "type": "text",
                                    "defaultFromUiSetting": "demo_query",
                                }
                            ],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        projects = self.gateway.list_projects()
        self.assertEqual("query", projects[0]["actions"][0]["parameters"][0]["id"])
        self.assertEqual("saved value", projects[0]["actions"][0]["parameters"][0]["default"])

        job = await self.gateway.create_job(
            ProjectJobCreate(project_id="demo", action="read", parameters={"query": "runtime value"})
        )
        self.assertEqual("queued", job.state)

    async def test_create_job_applies_ui_default_parameters_when_omitted(self):
        (Path(self.temporary_directory.name) / "projects" / "demo" / "data").mkdir(parents=True, exist_ok=True)
        (Path(self.temporary_directory.name) / "projects" / "demo" / "data" / "ui_settings.json").write_text(
            json.dumps({"demo_query": "saved value"}),
            encoding="utf-8",
        )
        (Path(self.temporary_directory.name) / "integrations" / "demo" / "adapter.json").write_text(
            json.dumps(
                {
                    "runtime": {"entrypoint": "main.py", "venvCandidates": []},
                    "actions": {
                        "read": {
                            "arguments": ["status"],
                            "parameters": [
                                {
                                    "id": "query",
                                    "defaultFromUiSetting": "demo_query",
                                }
                            ],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        job = await self.gateway.create_job(ProjectJobCreate(project_id="demo", action="read", parameters={}))
        self.assertEqual("saved value", job.parameters["query"])

    def test_project_output_alert_detects_vinted_login_required(self):
        alert = self.gateway._project_output_alert(
            '__VINTED_LOGIN_REQUIRED__:{"current_url":"https://www.vinted.it/catalog","marker_present":false}'
        )
        self.assertIsNotNone(alert)
        self.assertEqual("vinted_login_required", alert["kind"])
        self.assertIn("login", alert["summary"].lower())

    def test_project_output_alert_detects_vinted_page_not_found(self):
        alert = self.gateway._project_output_alert(
            '__VINTED_ACCESS__:{"current_url":"https://www.vinted.it/items/123","page_not_found":true,"marker_present":false}'
        )
        self.assertIsNotNone(alert)
        self.assertEqual("vinted_page_not_found", alert["kind"])

    async def test_deduplicates_repeated_live_project_alerts_until_state_changes(self):
        events: list[object] = []

        async def emit(event):
            events.append(event)

        gateway = ProjectGateway(Path(self.temporary_directory.name), emit, self.store)
        job = ProjectJob(project_id="demo", action="read", parameters={}, agent_id="specialist")
        try:
            await gateway._handle_project_output_line(
                job,
                '__VINTED_ACCESS__:{"current_url":"https://www.vinted.it/catalog","marker_present":false,"page_not_found":false}',
            )
            await gateway._handle_project_output_line(
                job,
                '__VINTED_ACCESS__:{"current_url":"https://www.vinted.it/catalog","marker_present":false,"page_not_found":false}',
            )
            await gateway._handle_project_output_line(
                job,
                '__VINTED_ACCESS__:{"current_url":"https://www.vinted.it/catalog","marker_present":true,"page_not_found":false}',
            )
        finally:
            await gateway.shutdown()

        self.assertEqual(2, len(events))
        self.assertEqual("vinted_marker_missing", events[0].data["alert"]["kind"])
        self.assertEqual("vinted_marker_found", events[1].data["alert"]["kind"])
        messages = self.store.load_agent_chat_messages("specialist", limit_turns=10)
        self.assertTrue(any("Vinted account marker missing" in message.content for message in messages))

    async def test_deduplicates_repeated_login_required_alerts_for_same_job_state(self):
        events: list[object] = []

        async def emit(event):
            events.append(event)

        gateway = ProjectGateway(Path(self.temporary_directory.name), emit, self.store)
        job = ProjectJob(project_id="demo", action="read", parameters={}, agent_id="specialist")
        try:
            await gateway._handle_project_output_line(
                job,
                '__VINTED_LOGIN_REQUIRED__:{"current_url":"https://www.vinted.it/catalog","marker_present":false}',
            )
            await gateway._handle_project_output_line(
                job,
                '__VINTED_LOGIN_REQUIRED__:{"current_url":"https://www.vinted.it/catalog","marker_present":false}',
            )
            await gateway._handle_project_output_line(
                job,
                '__VINTED_ACCESS__:{"current_url":"https://www.vinted.it/catalog","marker_present":true,"page_not_found":false}',
            )
            await gateway._handle_project_output_line(
                job,
                '__VINTED_LOGIN_REQUIRED__:{"current_url":"https://www.vinted.it/catalog","marker_present":false}',
            )
        finally:
            await gateway.shutdown()

        self.assertEqual(3, len(events))
        self.assertEqual("vinted_login_required", events[0].data["alert"]["kind"])
        self.assertEqual("vinted_marker_found", events[1].data["alert"]["kind"])
        self.assertEqual("vinted_login_required", events[2].data["alert"]["kind"])
        messages = self.store.load_agent_chat_messages("specialist", limit_turns=10)
        self.assertTrue(any("Vinted login required" in message.content for message in messages))

    async def test_cancel_job_marks_running_job_as_stopped(self):
        job = ProjectJob(project_id="demo", action="read", parameters={}, agent_id="specialist", state="running")
        self.gateway.jobs[job.id] = job

        class FakeProcess:
            def __init__(self):
                self.returncode = None
                self.terminated = False

            def terminate(self):
                self.terminated = True
                self.returncode = -15

            def kill(self):
                self.returncode = -9

            async def wait(self):
                return self.returncode

        fake = FakeProcess()
        self.gateway.processes[job.id] = fake

        cancelled = await self.gateway.cancel_job(job.id)

        self.assertTrue(fake.terminated)
        self.assertEqual("failed", cancelled.state)
        self.assertEqual("Stopped by user.", cancelled.error)

    async def test_report_job_failure_uses_error_reporter(self):
        reported: list[dict] = []

        class FakeReporter:
            async def report(self, **payload):
                reported.append(payload)
                return {"ok": True}

        gateway = ProjectGateway(
            Path(self.temporary_directory.name),
            self.gateway.emit,
            self.store,
            error_reporter=FakeReporter(),
        )
        entry = gateway._project_entry("demo")
        job = ProjectJob(project_id="demo", action="read", parameters={"query": "example"}, agent_id="specialist")
        try:
            await gateway._report_job_failure(job, entry, RuntimeError("boom"))
        finally:
            await gateway.shutdown()

        self.assertEqual(1, len(reported))
        self.assertEqual("project.job.failed", reported[0]["source"])
        self.assertEqual("demo", reported[0]["context"]["project_id"])
        self.assertEqual(job.id, reported[0]["context"]["job_id"])

    async def test_blocking_alert_reports_once_through_error_reporter(self):
        reported: list[dict] = []

        class FakeReporter:
            async def report(self, **payload):
                reported.append(payload)
                return {"ok": True}

        gateway = ProjectGateway(
            Path(self.temporary_directory.name),
            self.gateway.emit,
            self.store,
            error_reporter=FakeReporter(),
        )
        job = ProjectJob(project_id="demo", action="read", parameters={}, agent_id="specialist")
        try:
            await gateway._handle_project_output_line(
                job,
                '__VINTED_LOGIN_REQUIRED__:{"current_url":"https://www.vinted.it/catalog","marker_present":false}',
            )
            await gateway._handle_project_output_line(
                job,
                '__VINTED_LOGIN_REQUIRED__:{"current_url":"https://www.vinted.it/catalog","marker_present":false}',
            )
        finally:
            await gateway.shutdown()

        self.assertEqual(1, len(reported))
        self.assertEqual("project.job.blocked", reported[0]["source"])
        self.assertEqual("alert", reported[0]["context"]["phase"])

    def test_parameter_arguments_emit_negative_flag_for_explicit_false_checkbox(self):
        arguments = ProjectGateway._parameter_arguments(
            {"auto-submit-offers": False, "discord-deal-notifications": True},
            [
                {"id": "auto-submit-offers", "type": "checkbox", "emitFalseFlag": True},
                {"id": "discord-deal-notifications", "type": "checkbox"},
            ],
        )

        self.assertIn("--no-auto-submit-offers", arguments)
        self.assertIn("--discord-deal-notifications", arguments)

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

    def test_completed_project_job_output_is_saved_for_agent_chat(self):
        job = ProjectJob(
            project_id="demo",
            action="read",
            parameters={"query": "example"},
            agent_id="specialist",
        )
        job.state = "completed"
        job.updated_at = datetime.now(timezone.utc)
        job.result = {
            "source": "vinted",
            "command": "vinted.search",
            "row_count": 2,
            "normalized": {
                "meta_summary": {
                    "search_term": "charm",
                    "deal_hunter_enabled": True,
                    "deal_hunter_matches": 1,
                },
                "rows": [
                    {
                        "name": "Pandora charm",
                        "price": "12,00 EUR",
                        "loaded_at": "2 hours ago",
                        "deal_hunter_label": "hot listing",
                        "link": "https://example.test/items/1",
                    },
                    {
                        "name": "Bracelet",
                        "price": "8,00 EUR",
                        "link": "https://example.test/items/2",
                    },
                ],
            },
        }

        self.gateway._store_agent_job_message(job)

        messages = self.store.load_agent_chat_messages("specialist")
        self.assertTrue(messages)
        last = messages[-1]
        self.assertIsInstance(last, AgentChatMessage)
        self.assertEqual(f"{job.id}-project-output", last.id)
        self.assertIn("Project job completed.", last.content)
        self.assertIn("Deal hunter matches: 1", last.content)
        self.assertIn("Pandora charm", last.content)
        self.assertEqual("https://example.test/items/1", last.sources[0]["url"])


if __name__ == "__main__":
    unittest.main()
