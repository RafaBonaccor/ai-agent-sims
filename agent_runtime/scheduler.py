from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Optional

from .models import ProjectRepeatMode, ProjectScheduleMode, utc_now


ScheduledCallback = Callable[[], Awaitable[None]]


class ScheduledTaskRunner:
    """Shared async runner for delayed runtime work.

    Project jobs and agent tasks use the same timing primitive, so cancellation,
    delay calculation and shutdown behavior stay consistent.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.running: set[asyncio.Task[None]] = set()

    def start(self, coro: Awaitable[None], name: str) -> asyncio.Task[None]:
        task = asyncio.create_task(coro, name=name)
        self.running.add(task)
        task.add_done_callback(self.running.discard)
        return task

    def schedule_at(self, name: str, run_at: datetime, callback: ScheduledCallback) -> asyncio.Task[None]:
        return self.start(self._run_at(name, run_at, callback), name=name)

    async def _run_at(self, name: str, run_at: datetime, callback: ScheduledCallback) -> None:
        target = normalize_datetime(run_at)
        delay = max(0.0, (target - utc_now()).total_seconds())
        if delay:
            self.logger.info("scheduled_waiting name=%s run_at=%s delay_seconds=%.2f", name, target.isoformat(), delay)
            await asyncio.sleep(delay)
        await callback()

    async def shutdown(self) -> None:
        for task in tuple(self.running):
            task.cancel()
        if self.running:
            await asyncio.gather(*self.running, return_exceptions=True)


def resolve_schedule(
    schedule_mode: ProjectScheduleMode,
    scheduled_for: Optional[datetime],
    cron_expression: str,
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    if schedule_mode == ProjectScheduleMode.IMMEDIATE:
        return None
    if schedule_mode == ProjectScheduleMode.AT:
        if scheduled_for is None:
            raise ValueError("scheduled_for is required for at schedule mode")
        return normalize_datetime(scheduled_for)
    if schedule_mode == ProjectScheduleMode.CRON:
        if not cron_expression.strip():
            raise ValueError("cron_expression is required for cron schedule mode")
        return next_cron_time(cron_expression.strip(), now or utc_now())
    raise ValueError(f"Unsupported schedule mode: {schedule_mode}")


def next_followup_time(
    *,
    schedule_mode: ProjectScheduleMode,
    scheduled_for: Optional[datetime],
    cron_expression: str,
    repeat_mode: ProjectRepeatMode,
    weekdays: list[int],
    updated_at: Optional[datetime] = None,
) -> Optional[datetime]:
    if schedule_mode == ProjectScheduleMode.CRON and cron_expression.strip():
        return next_cron_time(cron_expression.strip(), updated_at or utc_now())
    if schedule_mode != ProjectScheduleMode.AT or scheduled_for is None:
        return None
    base = normalize_datetime(scheduled_for)
    if repeat_mode == ProjectRepeatMode.ONCE:
        return None
    if repeat_mode == ProjectRepeatMode.DAILY:
        return base + timedelta(days=1)
    if repeat_mode == ProjectRepeatMode.WEEKDAYS and weekdays:
        return next_weekday_occurrence(base, weekdays)
    return None


def normalize_weekdays(weekdays: list[int]) -> list[int]:
    return sorted({day for day in weekdays if 0 <= int(day) <= 6})


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def next_weekday_occurrence(base: datetime, weekdays: list[int]) -> Optional[datetime]:
    normalized = normalize_datetime(base).replace(second=0, microsecond=0)
    allowed = set(normalize_weekdays(weekdays))
    if not allowed:
        return None
    candidate = normalized + timedelta(days=1)
    for _index in range(8):
        if candidate.weekday() in allowed:
            return candidate
        candidate += timedelta(days=1)
    return None


def next_cron_time(expression: str, start: datetime) -> datetime:
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("cron_expression must have 5 fields: minute hour day month weekday")
    current = normalize_datetime(start).replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = current + timedelta(days=366)
    while current <= limit:
        if (
            cron_field_matches(current.minute, fields[0], 0, 59)
            and cron_field_matches(current.hour, fields[1], 0, 23)
            and cron_field_matches(current.day, fields[2], 1, 31)
            and cron_field_matches(current.month, fields[3], 1, 12)
            and cron_weekday_matches(current, fields[4])
        ):
            return current
        current += timedelta(minutes=1)
    raise ValueError("cron_expression does not resolve to a future execution within 1 year")


def cron_weekday_matches(moment: datetime, field: str) -> bool:
    cron_value = (moment.weekday() + 1) % 7
    values = cron_field_values(field, 0, 7)
    return cron_value in values or (cron_value == 0 and 7 in values)


def cron_field_matches(value: int, field: str, minimum: int, maximum: int) -> bool:
    return value in cron_field_values(field, minimum, maximum)


def cron_field_values(field: str, minimum: int, maximum: int) -> set[int]:
    field = field.strip()
    if field == "*":
        return set(range(minimum, maximum + 1))
    values: set[int] = set()
    for token in field.split(","):
        token = token.strip()
        if not token:
            continue
        if "/" in token:
            base, step_text = token.split("/", 1)
            step = max(1, int(step_text))
            if base == "*":
                start, end = minimum, maximum
            elif "-" in base:
                start_text, end_text = base.split("-", 1)
                start, end = int(start_text), int(end_text)
            else:
                start = end = int(base)
            values.update(range(start, end + 1, step))
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            values.update(range(int(start_text), int(end_text) + 1))
            continue
        values.add(int(token))
    normalized = {value for value in values if minimum <= value <= maximum}
    if maximum == 7 and 7 in values:
        normalized.add(0)
    return normalized
