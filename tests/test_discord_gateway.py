import tempfile
import unittest
from pathlib import Path

from agent_runtime.discord_gateway import (
    DiscordGateway,
    DiscordGatewayConfig,
    chunk_discord_message,
    parse_text_command,
)
from agent_runtime.engine import AgentRuntime
from agent_runtime.models import AgentDefinition, RuntimeEvent


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


if __name__ == "__main__":
    unittest.main()
