import unittest
from datetime import datetime

from alive_forever.core.scheduler import ScheduleConfig, TimeWindow, get_next_transition, is_schedule_active


class ScheduleLogicTests(unittest.TestCase):
    def test_disabled_schedule_is_always_active(self):
        schedule = ScheduleConfig(enabled=False, windows=[])
        self.assertTrue(is_schedule_active(schedule, datetime(2026, 4, 9, 3, 15)))

    def test_multiple_windows_same_day(self):
        schedule = ScheduleConfig(
            enabled=True,
            windows=[
                TimeWindow(start="09:00", end="12:00", days=["thu"]),
                TimeWindow(start="13:00", end="17:00", days=["thu"]),
            ],
        )
        self.assertTrue(is_schedule_active(schedule, datetime(2026, 4, 9, 9, 30)))
        self.assertFalse(is_schedule_active(schedule, datetime(2026, 4, 9, 12, 30)))
        self.assertTrue(is_schedule_active(schedule, datetime(2026, 4, 9, 15, 45)))

    def test_cross_midnight_window_uses_previous_day(self):
        schedule = ScheduleConfig(
            enabled=True,
            windows=[TimeWindow(start="22:00", end="06:00", days=["thu"])],
        )
        self.assertTrue(is_schedule_active(schedule, datetime(2026, 4, 9, 23, 0)))
        self.assertTrue(is_schedule_active(schedule, datetime(2026, 4, 10, 1, 0)))
        self.assertFalse(is_schedule_active(schedule, datetime(2026, 4, 10, 6, 30)))

    def test_next_transition_prefers_nearest_boundary(self):
        schedule = ScheduleConfig(
            enabled=True,
            windows=[
                TimeWindow(start="09:00", end="12:00", days=["thu"]),
                TimeWindow(start="13:00", end="17:00", days=["thu"]),
            ],
        )
        transition = get_next_transition(schedule, datetime(2026, 4, 9, 12, 15))
        self.assertEqual("active", transition[0])
        self.assertEqual(datetime(2026, 4, 9, 13, 0), transition[1])

    def test_exact_minutes_include_start_and_exclude_end(self):
        for end in ("16:15", "16:30", "16:37"):
            with self.subTest(end=end):
                schedule = ScheduleConfig(enabled=True, windows=[TimeWindow("09:15", end, ["thu"])])
                self.assertFalse(is_schedule_active(schedule, datetime(2026, 4, 9, 9, 14, 59)))
                self.assertTrue(is_schedule_active(schedule, datetime(2026, 4, 9, 9, 15)))
                end_at = datetime.fromisoformat("2026-04-09T" + end)
                self.assertFalse(is_schedule_active(schedule, end_at))
                self.assertEqual(("scheduled_off", end_at), get_next_transition(schedule, datetime(2026, 4, 9, 10)))

    def test_transition_skips_overlapping_and_adjacent_boundaries(self):
        schedule = ScheduleConfig(enabled=True, windows=[
            TimeWindow("09:00", "12:00", ["thu"]),
            TimeWindow("11:30", "16:15", ["thu"]),
            TimeWindow("16:15", "16:30", ["thu"]),
        ])
        self.assertEqual(("scheduled_off", datetime(2026, 4, 9, 16, 30)),
                         get_next_transition(schedule, datetime(2026, 4, 9, 10)))


if __name__ == "__main__":
    unittest.main()