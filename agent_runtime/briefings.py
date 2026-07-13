from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .engine import AgentRuntime
from .models import RuntimeEvent, TaskCreate, TaskRecord
from .scheduler import ScheduledTaskRunner


LOGGER = logging.getLogger("agent_lab.briefings")
DEFAULT_AI_NEWS_AGENT_ID = "ai-news-navigator"


@dataclass(frozen=True)
class MorningBriefingConfig:
    enabled: bool = True
    agent_id: str = DEFAULT_AI_NEWS_AGENT_ID
    local_time: time = time(hour=8, minute=0)
    timezone: str = "Europe/Rome"
    run_missed: bool = False
    topic: str = "ultime notizie sull'intelligenza artificiale"

    @classmethod
    def from_env(cls) -> "MorningBriefingConfig":
        return cls(
            enabled=parse_bool(os.environ.get("AGENT_LAB_AI_NEWS_BRIEFING", "1"), default=True),
            agent_id=os.environ.get("AGENT_LAB_AI_NEWS_AGENT", DEFAULT_AI_NEWS_AGENT_ID).strip()
            or DEFAULT_AI_NEWS_AGENT_ID,
            local_time=parse_local_time(os.environ.get("AGENT_LAB_AI_NEWS_TIME", "08:00")),
            timezone=os.environ.get("AGENT_LAB_AI_NEWS_TIMEZONE", "Europe/Rome").strip() or "Europe/Rome",
            run_missed=parse_bool(os.environ.get("AGENT_LAB_AI_NEWS_RUN_MISSED", "0"), default=False),
            topic=os.environ.get("AGENT_LAB_AI_NEWS_TOPIC", "ultime notizie sull'intelligenza artificiale").strip()
            or "ultime notizie sull'intelligenza artificiale",
        )


class MorningBriefingScheduler:
    """Creates a daily AI news briefing task for a dedicated agent."""

    def __init__(
        self,
        runtime: AgentRuntime,
        config: Optional[MorningBriefingConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.runtime = runtime
        self.config = config or MorningBriefingConfig.from_env()
        self.logger = logger or LOGGER
        self.runner = ScheduledTaskRunner(self.logger)
        self.scheduled_for: Optional[datetime] = None

    async def start(self) -> None:
        if not self.config.enabled:
            self.logger.info("ai_news_briefing_disabled")
            return
        if self.config.agent_id not in self.runtime.agents:
            self.logger.warning("ai_news_briefing_disabled reason=missing_agent agent=%s", self.config.agent_id)
            return
        if self.runner.running:
            return
        self._schedule_next()
        self.logger.info(
            "ai_news_briefing_enabled agent=%s time=%s timezone=%s",
            self.config.agent_id,
            self.config.local_time.strftime("%H:%M"),
            self.config.timezone,
        )

    async def shutdown(self) -> None:
        await self.runner.shutdown()
        self.scheduled_for = None

    def status(self, now: Optional[datetime] = None) -> dict[str, Any]:
        zone = self._zone()
        reference = now.astimezone(zone) if now else datetime.now(zone)
        next_run = self.next_run_at(reference)
        return {
            "enabled": self.config.enabled,
            "agent_id": self.config.agent_id,
            "agent_present": self.config.agent_id in self.runtime.agents,
            "local_time": self.config.local_time.strftime("%H:%M"),
            "timezone": self.config.timezone,
            "next_run_at": (self.scheduled_for or next_run).isoformat(),
            "run_missed": self.config.run_missed,
            "topic": self.config.topic,
            "created_today": self._existing_task_for_date(reference.date().isoformat()) is not None,
        }

    def next_run_at(self, now: Optional[datetime] = None) -> datetime:
        zone = self._zone()
        reference = now.astimezone(zone) if now else datetime.now(zone)
        today_run = datetime.combine(reference.date(), self.config.local_time, tzinfo=zone)
        if reference < today_run:
            return today_run
        if self.config.run_missed and self._existing_task_for_date(reference.date().isoformat()) is None:
            return reference
        return today_run + timedelta(days=1)

    async def create_briefing(self, now: Optional[datetime] = None, force: bool = False) -> TaskRecord:
        zone = self._zone()
        reference = now.astimezone(zone) if now else datetime.now(zone)
        date_key = reference.date().isoformat()
        if self.config.agent_id not in self.runtime.agents:
            raise KeyError(f"Briefing agent not found: {self.config.agent_id}")
        existing = self._existing_task_for_date(date_key)
        if existing and not force:
            return existing

        task = await self.runtime.create_task(
            TaskCreate(
                title=self._title(date_key),
                description=self._prompt(reference),
                capability="news",
                priority=4,
                requested_agent_id=self.config.agent_id,
                channel="chat",
            )
        )
        await self.runtime.publish(
            RuntimeEvent(
                type="briefing.created",
                entity_id=task.id,
                agent_id=self.config.agent_id,
                task_id=task.id,
                summary=f"AI morning briefing queued for {date_key}.",
                data={"date": date_key, "agent_id": self.config.agent_id},
            )
        )
        return task

    def _schedule_next(self) -> None:
        self.scheduled_for = self.next_run_at()
        self.runner.schedule_at("ai-news-morning-briefing", self.scheduled_for, self._run_due)

    async def _run_due(self) -> None:
        try:
            await self.create_briefing(datetime.now(self._zone()), force=False)
        except Exception as error:
            self.logger.exception("ai_news_briefing_failed error=%s", error)
        finally:
            if self.config.enabled and self.config.agent_id in self.runtime.agents:
                self._schedule_next()

    def _zone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.config.timezone)
        except ZoneInfoNotFoundError:
            self.logger.warning("ai_news_invalid_timezone timezone=%s fallback=UTC", self.config.timezone)
            return ZoneInfo("UTC")

    @staticmethod
    def _title(date_key: str) -> str:
        return f"AI morning briefing — {date_key}"

    def _prompt(self, reference: datetime) -> str:
        date_label = reference.date().isoformat()
        return (
            f"Prepara il riepilogo mattutino del {date_label} sulle {self.config.topic}.\n\n"
            "Obiettivo: trovare notizie recenti e rilevanti pubblicate nelle ultime 24-36 ore. "
            "Usa ricerca web o navigazione browser se disponibili.\n\n"
            "Formato richiesto in italiano:\n"
            "1. TL;DR in 3 righe.\n"
            "2. 5-8 notizie ordinate per impatto, ognuna con: titolo, cosa è successo, perché conta, fonte/link.\n"
            "3. Separa chiaramente fatti confermati, rumor e analisi.\n"
            "4. Chiudi con 3 trend da monitorare oggi.\n\n"
            "Non inventare fonti. Se non riesci a verificare una notizia, dichiaralo esplicitamente."
        )

    def _existing_task_for_date(self, date_key: str) -> Optional[TaskRecord]:
        title = self._title(date_key)
        for task in self.runtime.tasks.values():
            if task.title == title and task.requested_agent_id == self.config.agent_id and task.channel == "chat":
                return task
        return None


def parse_local_time(value: str) -> time:
    raw = str(value or "08:00").strip()
    try:
        hour_text, minute_text = raw.split(":", maxsplit=1)
        hour = int(hour_text)
        minute = int(minute_text)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour=hour, minute=minute)
    except (ValueError, TypeError):
        pass
    LOGGER.warning("ai_news_invalid_time value=%s fallback=08:00", value)
    return time(hour=8, minute=0)


def parse_bool(value: str, default: bool = False) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on", "enabled"}:
        return True
    if raw in {"0", "false", "no", "off", "disabled"}:
        return False
    return default
