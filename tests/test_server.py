import asyncio
import tempfile
import unittest
from pathlib import Path

from agent_runtime import server
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
        server.app.state.runtime = self.runtime

    async def asyncTearDown(self):
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


if __name__ == "__main__":
    unittest.main()
