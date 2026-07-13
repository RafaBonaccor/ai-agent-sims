import asyncio
import tempfile
import unittest
from pathlib import Path

from agent_runtime import server
from agent_runtime.briefings import MorningBriefingConfig, MorningBriefingScheduler
from agent_runtime.engine import AgentRuntime
from agent_runtime.models import AgentDefinition, TaskCreate


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        database = Path(self.temporary_directory.name) / "data" / "runtime.db"
        self.runtime = AgentRuntime(database, simulation_delay=0)
        await self.runtime.add_agent(
            AgentDefinition(
                id="orchestrator",
                name="Orchestrator",
                role="supervisor",
                capabilities=["planning"],
            )
        )
        await self.runtime.add_agent(
            AgentDefinition(
                id="specialist",
                name="Specialist",
                role="specialist",
                capabilities=["implementation"],
                toolsets=["browser"],
            )
        )
        await self.runtime.add_agent(
            AgentDefinition(
                id="ai-news-navigator",
                name="AI News Navigator",
                role="web-navigator",
                capabilities=["news"],
                toolsets=["web"],
            )
        )
        server.app.state.runtime = self.runtime
        server.app.state.ai_news_briefing = MorningBriefingScheduler(
            self.runtime,
            MorningBriefingConfig(enabled=True, agent_id="ai-news-navigator"),
        )

    async def asyncTearDown(self):
        await server.app.state.ai_news_briefing.shutdown()
        await self.runtime.shutdown()
        self.temporary_directory.cleanup()

    async def test_health_and_task_api_handlers(self):
        health = await server.health()
        self.assertEqual("ok", health["status"])
        self.assertTrue(health["features"]["browserControl"])

        task = await server.create_task(
            TaskCreate(
                title="Execute an API task",
                description="Verify server handler execution.",
                requested_agent_id="specialist",
            )
        )
        await asyncio.gather(*tuple(self.runtime.running_jobs))

        tasks = await server.list_tasks()
        completed = next(item for item in tasks if item.id == task.id)
        self.assertEqual("completed", completed.state.value)
        self.assertEqual("specialist", completed.assigned_agent_id)

    async def test_browser_session_api_handlers_use_runtime_browser_control(self):
        opened = await server.create_browser_session(
            server.BrowserSessionCreate(
                backend="mock",
                url="https://example.test",
                page_text="Server browser context",
            )
        )
        session_id = opened["session"]["id"]

        sessions = await server.list_browser_sessions()
        self.assertEqual([session_id], [item["id"] for item in sessions])

        current = await server.run_browser_command(
            session_id,
            server.BrowserCommandRequest(command="current_url"),
        )
        extracted = await server.run_browser_command(
            session_id,
            server.BrowserCommandRequest(command="extract", parameters={"selector": "body"}),
        )

        self.assertEqual("https://example.test", current["url"])
        self.assertEqual("Server browser context", extracted["value"])
        closed = await server.close_browser_session(session_id)
        self.assertTrue(closed["closed"])

    async def test_ai_news_briefing_api_creates_agent_task(self):
        status = await server.ai_news_briefing_status()
        self.assertTrue(status["enabled"])
        self.assertEqual("ai-news-navigator", status["agent_id"])

        task = await server.run_ai_news_briefing()
        self.assertEqual("ai-news-navigator", task.requested_agent_id)
        self.assertEqual("chat", task.channel)
        self.assertEqual("news", task.capability)


if __name__ == "__main__":
    unittest.main()
