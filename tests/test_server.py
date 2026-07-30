import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from agent_runtime import server
from agent_runtime.briefings import MorningBriefingConfig, MorningBriefingScheduler
from agent_runtime.engine import AgentRuntime
from agent_runtime.knowledge import KnowledgeWiki
from agent_runtime.models import AgentDefinition, DiscordBotSettings, SystemSettings, TaskCreate
from agent_runtime.project_gateway import ProjectGateway
from agent_runtime.secrets import SecretStore


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        database = Path(self.temporary_directory.name) / "data" / "runtime.db"
        self.runtime = AgentRuntime(database, simulation_delay=0)
        self.runtime.executor.workspace_root = Path(self.temporary_directory.name)
        self.runtime.knowledge_wiki = KnowledgeWiki(Path(self.temporary_directory.name) / "data" / "wiki")
        self.runtime.executor.wiki = self.runtime.knowledge_wiki
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
        server.app.state.secrets = SecretStore(Path(self.temporary_directory.name) / "data" / "secrets.json", backend="local-test")
        server.app.state.project_gateway = ProjectGateway(Path("/Users/rafael/Documents/Personal_workspace/ai-agent-sims"), self.runtime.publish, self.runtime.store)
        server.app.state.error_reporter = None
        server.app.state.ai_news_briefing = MorningBriefingScheduler(
            self.runtime,
            MorningBriefingConfig(enabled=True, agent_id="ai-news-navigator"),
        )
        server.app.state.discord_gateway = server.build_discord_gateway()

    async def asyncTearDown(self):
        await server.app.state.discord_gateway.shutdown()
        await server.app.state.project_gateway.shutdown()
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

    async def test_wiki_proposal_api_handlers(self):
        proposal = self.runtime.knowledge_wiki.propose(
            agent_id="specialist",
            title="Memory retrieval note",
            content="Use shared wiki retrieval before answering implementation tasks.",
            source="task-memory",
        )

        proposals = await server.list_wiki_proposals()
        self.assertEqual([proposal.name], [item.name for item in proposals])

        resolved = await server.resolve_wiki_proposal(
            proposal.name,
            server.WikiProposalResolveRequest(
                status="approved",
                reviewer="Rafael",
                reason="Reviewed and accepted.",
            ),
        )
        self.assertTrue(resolved.name.startswith("approved-"))
        self.assertIn("Reviewed and accepted.", resolved.content)

    async def test_wiki_page_search_and_maintenance_api_handlers(self):
        self.runtime.knowledge_wiki.update_page(
            "knowledge-implementation",
            "# Implementation\n\n## Memory\nUse canonical wiki pages for reviewed knowledge.",
            agent_id="specialist",
            source="test",
        )

        pages = await server.list_wiki_pages()
        self.assertIn("knowledge-implementation.md", [page.name for page in pages])

        page = await server.get_wiki_page("knowledge-implementation.md")
        self.assertIn("reviewed knowledge", page.content)

        result = await server.search_wiki("canonical reviewed knowledge")
        self.assertTrue(result.pages)
        self.assertIn("reviewed knowledge", result.pages[0]["content"])

        maintenance = await server.run_wiki_maintenance()
        self.assertGreaterEqual(maintenance.pages_scanned, 1)
        self.assertEqual("index.md", maintenance.index_page)

    async def test_wiki_search_route_is_registered_before_page_catchall(self):
        paths = [getattr(route, "path", "") for route in server.app.routes]
        search_index = paths.index("/api/wiki/search")
        catchall_index = paths.index("/api/wiki/pages/{name:path}")
        self.assertLess(search_index, catchall_index)

    async def test_report_client_error_uses_runtime_error_reporter(self):
        reported: list[dict] = []

        class FakeReporter:
            async def report(self, **payload):
                reported.append(payload)
                return {"ok": True}

        server.app.state.error_reporter = FakeReporter()
        result = await server.report_client_error(
            server.ErrorReportRequest(
                source="ui.window.error",
                message="Unhandled browser error",
                context={"phase": "ui"},
                screenshot_data_url="data:image/png;base64,ZmFrZQ==",
            )
        )

        self.assertTrue(result["accepted"])
        self.assertEqual(1, len(reported))
        self.assertEqual("ui.window.error", reported[0]["source"])
        self.assertEqual("Unhandled browser error", reported[0]["message"])

    async def test_set_discord_bot_secret_reloads_gateway_and_persists_token(self):
        await server.update_system_settings(
            SystemSettings(discord=DiscordBotSettings(enabled=True, message_content=True))
        )
        mocked_reload = AsyncMock()
        original_reload = server.reload_discord_gateway
        server.reload_discord_gateway = mocked_reload
        try:
            result = await server.set_discord_bot_secret(
                server.SecretValue(api_key="discord-bot-token-1234567890")
            )
        finally:
            server.reload_discord_gateway = original_reload

        self.assertTrue(result["discord_bot_configured"])
        self.assertEqual("discord-bot-token-1234567890", server.app.state.secrets.get_discord_bot_token())
        mocked_reload.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
