import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_runtime.discord_gateway import (
    DiscordGateway,
    DiscordGatewayConfig,
    chunk_discord_message,
    parse_text_command,
)
from agent_runtime.discord_projects import DiscordAttachment, DiscordProjectBridge
from agent_runtime.engine import AgentRuntime
from agent_runtime.models import AgentDefinition, RuntimeEvent
from agent_runtime.project_gateway import ProjectJob


class DiscordGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.runtime = AgentRuntime(Path(self.temporary_directory.name) / "runtime.db", simulation_delay=0)
        await self.runtime.add_agent(
            AgentDefinition(id="researcher", name="Researcher", role="researcher")
        )

    async def asyncTearDown(self):
        await self.runtime.shutdown()
        self.temporary_directory.cleanup()

    def test_parse_prefix_commands(self):
        self.assertEqual("agents", parse_text_command("!agents").action)

        use = parse_text_command("!use researcher")
        self.assertEqual("use", use.action)
        self.assertEqual("researcher", use.agent_id)

        ask = parse_text_command("!ask researcher ciao come va")
        self.assertEqual("ask", ask.action)
        self.assertEqual("researcher", ask.agent_id)
        self.assertEqual("ciao come va", ask.prompt)

        codex = parse_text_command("!codex spiegami questo file")
        self.assertEqual("codex", codex.action)
        self.assertEqual("spiegami questo file", codex.prompt)

    def test_parse_mention_command_with_default_agent(self):
        ask = parse_text_command(
            "ciao come va",
            default_agent_id="researcher",
            mentioned=True,
        )
        self.assertEqual("ask", ask.action)
        self.assertEqual("researcher", ask.agent_id)
        self.assertEqual("ciao come va", ask.prompt)

    def test_chunk_discord_message(self):
        chunks = chunk_discord_message("x" * 4100, limit=1900)
        self.assertEqual(3, len(chunks))
        self.assertTrue(all(len(chunk) <= 1900 for chunk in chunks))

    async def test_submit_chat_creates_runtime_chat_task(self):
        sent = []
        gateway = DiscordGateway(self.runtime, DiscordGatewayConfig())

        async def send(message):
            sent.append(message)

        task = await gateway.submit_chat("researcher", "ciao come va", send)

        self.assertEqual("chat", task.channel)
        self.assertEqual("researcher", task.requested_agent_id)
        self.assertIn(task.id, gateway.pending)

    async def test_submit_codex_chat_uses_codex_agent(self):
        sent = []
        await self.runtime.add_agent(
            AgentDefinition(
                id="codex",
                name="Codex",
                role="assistant",
                model={"provider": "openai", "model": "gpt-5.1-codex", "temperature": 0.2},
            )
        )
        gateway = DiscordGateway(self.runtime, DiscordGatewayConfig())

        async def send(message):
            sent.append(message)

        task = await gateway.submit_chat("codex", "ciao", send)

        self.assertEqual("chat", task.channel)
        self.assertEqual("codex", task.requested_agent_id)
        self.assertIn(task.id, gateway.pending)

    async def test_send_codex_prompt_delegates_to_bridge(self):
        gateway = DiscordGateway(self.runtime, DiscordGatewayConfig())

        class FakeBridge:
            async def ask(self, channel_key, prompt):
                return type(
                    "Result",
                    (),
                    {
                        "messages": ["🧠 step 1", "final answer"],
                        "final_response": "final answer",
                        "session_id": "thread-1",
                    },
                )()

        gateway.codex_bridge = FakeBridge()

        result = await gateway.send_codex_prompt("channel-1", "ciao")

        self.assertEqual("final answer", result.final_response)

    async def test_send_codex_result_sends_all_messages(self):
        gateway = DiscordGateway(self.runtime, DiscordGatewayConfig())
        sent: list[str] = []

        async def send(message: str):
            sent.append(message)

        result = type(
            "Result",
            (),
            {"messages": ["🧠 step 1", "```text\n$ echo hello\nhello\n```", "final answer"], "final_response": "final answer"},
        )()

        await gateway.send_codex_result(send, result)

        self.assertEqual(["> 🧠 step 1", "```text\n$ echo hello\nhello\n```", "final answer"], sent)

    async def test_codex_model_status_and_updates_are_exposed(self):
        gateway = DiscordGateway(self.runtime, DiscordGatewayConfig())
        gateway.codex_bridge.set_channel_model("123", "gpt-5.1-codex")

        self.assertIn("gpt-5.1-codex", gateway.format_codex_model_status("123"))
        self.assertIn("not set", gateway.format_codex_model_status("999"))
        self.assertIn("gpt-5.1-codex", gateway.format_codex_model_status("123", override="gpt-5.1-codex"))

    async def test_submit_chat_accepts_short_prompt(self):
        sent = []
        gateway = DiscordGateway(self.runtime, DiscordGatewayConfig())

        async def send(message):
            sent.append(message)

        task = await gateway.submit_chat("researcher", "ok", send)
        self.assertEqual("Chat: ok", task.title)
        self.assertEqual("ok", task.description)

    async def test_runtime_result_is_sent_to_pending_discord_reply(self):
        sent = []
        gateway = DiscordGateway(self.runtime, DiscordGatewayConfig())

        async def send(message):
            sent.append(message)

        task = await gateway.submit_chat("researcher", "ciao", send)
        await gateway._handle_runtime_event(
            RuntimeEvent(
                type="protocol.message",
                task_id=task.id,
                summary="result",
                data={
                    "message": {
                        "type": "task.result",
                        "payload": {"summary": "Sto bene."},
                    }
                },
            )
        )

        self.assertEqual([], list(gateway.pending))
        self.assertIn("Sto bene.", sent[0])

    async def test_project_job_event_is_sent_to_pending_discord_reply(self):
        sent = []
        gateway = DiscordGateway(self.runtime, DiscordGatewayConfig())

        async def send(message):
            sent.append(message)

        gateway.pending_project_jobs["job-123"] = (
            type("Pending", (), {"job_id": "job-123", "project_id": "main-scraper", "action": "vinted.upload", "agent_id": "researcher"})(),
            send,
        )

        await gateway._handle_runtime_event(
            RuntimeEvent(
                type="project.job.completed",
                entity_id="job-123",
                summary="done",
                data={"job": {"id": "job-123", "action": "vinted.upload", "result": {"command": "vinted_upload"}}},
            )
        )

        self.assertEqual([], list(gateway.pending_project_jobs))
        self.assertIn("completed", sent[0])

    def test_parse_vinted_upload_text_command(self):
        parsed = DiscordProjectBridge.parse_vinted_upload_text_command(
            "!upload researcher\nprice: 12.50",
            default_agent_id="researcher",
        )
        self.assertIsNotNone(parsed)
        self.assertEqual("vinted.upload", parsed.action)
        self.assertEqual("researcher", parsed.agent_id)

    def test_parse_vinted_upload_text_command_allows_empty_body(self):
        parsed = DiscordProjectBridge.parse_vinted_upload_text_command(
            "!upload researcher",
            default_agent_id="researcher",
        )
        self.assertIsNotNone(parsed)
        self.assertEqual("vinted.upload", parsed.action)
        self.assertEqual("researcher", parsed.agent_id)
        self.assertEqual("", parsed.payload["body"])

    def test_parse_vinted_upload_ai_photo_text_command_enables_photo_enhancement(self):
        parsed = DiscordProjectBridge.parse_vinted_upload_text_command(
            "!upload-ai-photo researcher\nprice: 12.50",
            default_agent_id="researcher",
        )
        self.assertIsNotNone(parsed)
        self.assertEqual("vinted.upload", parsed.action)
        self.assertEqual("researcher", parsed.agent_id)
        self.assertTrue(bool(parsed.payload["enhance_photos"]))

    def test_parse_codex_model_text_command(self):
        parsed = parse_text_command("!codex-model set gpt-5.1-codex")
        self.assertIsNotNone(parsed)
        self.assertEqual("codex_model", parsed.action)
        self.assertEqual("set", parsed.agent_id)
        self.assertEqual("gpt-5.1-codex", parsed.prompt)


class DiscordProjectBridgeTests(unittest.IsolatedAsyncioTestCase):
    class FakeGateway:
        def __init__(self):
            self.request = None

        async def create_job(self, request):
            self.request = request
            return ProjectJob(project_id=request.project_id, action=request.action, parameters=request.parameters, agent_id=request.agent_id)

    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.bridge = DiscordProjectBridge(Path(self.temporary_directory.name), self.FakeGateway())

    async def asyncTearDown(self):
        self.temporary_directory.cleanup()

    async def test_submit_vinted_upload_uses_price_from_text_attachment(self):
        photo = Path(self.temporary_directory.name) / "photo.png"
        photo.write_bytes(b"photo")

        async def fake_collect(_attachments):
            return ([str(photo.resolve())], {"price": "19.90", "category": "Braccialetti", "brand": "No Label", "condition": "Ottime", "material": "Acciaio"})

        self.bridge._collect_attachment_inputs = fake_collect

        job = await self.bridge.submit_vinted_upload(
            content="title: Charm\ndescription: Test\nprice: 7.00",
            attachments=[DiscordAttachment(url="https://example.test/meta.txt", filename="meta.txt", content_type="text/plain")],
            agent_id="researcher",
        )

        self.assertEqual("main-scraper", job.project_id)
        manifest_path = Path(self.bridge.project_gateway.request.parameters["items-file"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("19.90", manifest["items"][0]["price"])

    async def test_submit_vinted_upload_accepts_empty_body_when_attachment_contains_fields(self):
        photo = Path(self.temporary_directory.name) / "photo.png"
        photo.write_bytes(b"photo")

        async def fake_collect(_attachments):
            return (
                [str(photo.resolve())],
                {
                    "title": "Charm",
                    "description": "Test",
                    "price": "19.90",
                    "category": "Braccialetti",
                    "brand": "No Label",
                    "condition": "Ottime",
                    "material": "Acciaio",
                },
            )

        self.bridge._collect_attachment_inputs = fake_collect

        job = await self.bridge.submit_vinted_upload(
            content="",
            attachments=[DiscordAttachment(url="https://example.test/meta.txt", filename="meta.txt", content_type="text/plain")],
            agent_id="researcher",
        )

        manifest_path = Path(self.bridge.project_gateway.request.parameters["items-file"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("Charm", manifest["items"][0]["title"])
        self.assertEqual("19.90", manifest["items"][0]["price"])
        self.assertEqual("researcher", job.agent_id)

    async def test_submit_vinted_upload_can_enhance_photos_with_ai(self):
        photo = Path(self.temporary_directory.name) / "photo.png"
        photo.write_bytes(b"photo")
        enhanced = Path(self.temporary_directory.name) / "photo_ai.png"
        enhanced.write_bytes(b"photo-ai")

        async def fake_collect(_attachments):
            return (
                [str(photo.resolve())],
                {
                    "title": "Charm",
                    "description": "Test",
                    "price": "19.90",
                    "category": "Braccialetti",
                    "brand": "No Label",
                    "condition": "Ottime",
                    "material": "Acciaio",
                },
            )

        async def fake_enhance(paths):
            self.assertEqual([str(photo.resolve())], paths)
            return [str(enhanced.resolve())]

        self.bridge._collect_attachment_inputs = fake_collect
        self.bridge._enhance_vinted_upload_photos_with_ai = fake_enhance

        await self.bridge.submit_vinted_upload(
            content="",
            attachments=[DiscordAttachment(url="https://example.test/photo.png", filename="photo.png", content_type="image/png")],
            agent_id="researcher",
            enhance_photos=True,
        )

        manifest_path = Path(self.bridge.project_gateway.request.parameters["items-file"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual([str(enhanced.resolve())], manifest["items"][0]["photo_paths"])
        self.assertTrue(bool(manifest["items"][0]["openai_used"]))
        self.assertIn("gpt-image-2", manifest["items"][0]["openai_model"])

    def test_parse_vinted_upload_payload_supports_free_text(self):
        payload = self.bridge.parse_vinted_upload_payload(
            "\n".join(
                [
                    "upload researcher",
                    "Nome testing descrizione un test fico prezzo 10 euro materiale acciaio categoria gioielli",
                    "Immagine",
                ]
            )
        )

        self.assertEqual("testing", payload["title"])
        self.assertEqual("un test fico", payload["description"])
        self.assertEqual("10 euro", payload["price"])
        self.assertEqual("gioielli", payload["category"])
        self.assertEqual("No Label", payload["brand"])
        self.assertEqual("Ottime", payload["condition"])
        self.assertEqual("acciaio", payload["material"])

    async def test_submit_vinted_upload_reports_ai_error_when_payload_is_incomplete(self):
        photo = Path(self.temporary_directory.name) / "photo.png"
        photo.write_bytes(b"photo")

        async def fake_collect(_attachments):
            return ([str(photo.resolve())], {})

        self.bridge._collect_attachment_inputs = fake_collect

        with patch.object(
            self.bridge,
            "_structure_vinted_upload_payload_with_ai",
            side_effect=ValueError("OPENAI_API_KEY not found in the environment or project secret store."),
        ):
            with self.assertRaisesRegex(ValueError, "Discord AI structuring failed: OPENAI_API_KEY"):
                await self.bridge.submit_vinted_upload(
                    content='{"title":"Charm Pandora","description":"Silver charm"}',
                    attachments=[DiscordAttachment(url="https://example.test/photo.png", filename="photo.png", content_type="image/png")],
                    agent_id="researcher",
                )


if __name__ == "__main__":
    unittest.main()
