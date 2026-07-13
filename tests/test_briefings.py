import asyncio
import tempfile
import unittest
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from agent_runtime.briefings import MorningBriefingConfig, MorningBriefingScheduler
from agent_runtime.engine import AgentRuntime
from agent_runtime.models import AgentDefinition


class MorningBriefingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.runtime = AgentRuntime(Path(self.temporary_directory.name) / "runtime.db", simulation_delay=0)
        await self.runtime.add_agent(
            AgentDefinition(
                id="ai-news-navigator",
                name="AI News Navigator",
                role="web-navigator",
                capabilities=["news"],
                toolsets=["web", "browser"],
            )
        )
        self.config = MorningBriefingConfig(
            enabled=True,
            agent_id="ai-news-navigator",
            local_time=time(8, 0),
            timezone="Europe/Rome",
            run_missed=False,
        )
        self.scheduler = MorningBriefingScheduler(self.runtime, self.config)

    async def asyncTearDown(self):
        await self.scheduler.shutdown()
        await self.runtime.shutdown()
        self.temporary_directory.cleanup()

    async def test_manual_briefing_creates_chat_task_for_web_agent(self):
        now = datetime(2026, 7, 12, 9, 30, tzinfo=ZoneInfo("Europe/Rome"))

        task = await self.scheduler.create_briefing(now=now)
        await asyncio.gather(*tuple(self.runtime.running_jobs))

        self.assertEqual("ai-news-navigator", task.requested_agent_id)
        self.assertEqual("chat", task.channel)
        self.assertEqual("news", task.capability)
        self.assertIn("AI morning briefing — 2026-07-12", task.title)
        self.assertIn("ultime notizie", task.description)
        self.assertIn("fonti", task.description.lower())

    async def test_briefing_deduplicates_same_day(self):
        now = datetime(2026, 7, 12, 9, 30, tzinfo=ZoneInfo("Europe/Rome"))

        first = await self.scheduler.create_briefing(now=now)
        second = await self.scheduler.create_briefing(now=now)

        self.assertEqual(first.id, second.id)

    def test_next_run_uses_tomorrow_when_missed_runs_are_disabled(self):
        now = datetime(2026, 7, 12, 9, 30, tzinfo=ZoneInfo("Europe/Rome"))
        next_run = self.scheduler.next_run_at(now)

        self.assertEqual(datetime(2026, 7, 13, 8, 0, tzinfo=ZoneInfo("Europe/Rome")), next_run)


if __name__ == "__main__":
    unittest.main()
