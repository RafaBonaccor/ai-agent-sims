import unittest
from datetime import datetime, timedelta, timezone

from agent_runtime.models import ProjectRepeatMode, ProjectScheduleMode
from agent_runtime.scheduler import (
    next_cron_time,
    next_followup_time,
    next_weekday_occurrence,
    normalize_datetime,
    normalize_weekdays,
    resolve_schedule,
)


class SchedulerTests(unittest.TestCase):
    def test_resolves_cron_schedule(self):
        start = datetime(2026, 7, 12, 7, 59, tzinfo=timezone.utc)
        scheduled = resolve_schedule(ProjectScheduleMode.CRON, None, "0 8 * * *", now=start)
        self.assertEqual(datetime(2026, 7, 12, 8, 0, tzinfo=timezone.utc), scheduled)

    def test_daily_followup_moves_one_day(self):
        base = datetime(2026, 7, 12, 8, 0, tzinfo=timezone.utc)
        self.assertEqual(
            base + timedelta(days=1),
            next_followup_time(
                schedule_mode=ProjectScheduleMode.AT,
                scheduled_for=base,
                cron_expression="",
                repeat_mode=ProjectRepeatMode.DAILY,
                weekdays=[],
            ),
        )

    def test_weekday_normalization_and_next_occurrence(self):
        self.assertEqual([0, 2, 4], normalize_weekdays([4, 2, 2, 0, 9]))
        base = datetime(2026, 7, 9, 8, 0, tzinfo=timezone.utc)
        self.assertEqual(4, next_weekday_occurrence(base, [0, 2, 4]).weekday())

    def test_normalizes_naive_datetime_to_utc(self):
        value = datetime(2026, 7, 12, 8, 0)
        self.assertEqual(timezone.utc, normalize_datetime(value).tzinfo)

    def test_cron_rejects_invalid_expression(self):
        with self.assertRaisesRegex(ValueError, "5 fields"):
            next_cron_time("* * *", datetime(2026, 7, 12, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
