import unittest
from datetime import datetime

from alive_forever.core.scheduler import (
    DAY_ORDER,
    ScheduleConfig,
    TimeWindow,
    grid_to_windows,
    is_schedule_active,
    schedule_uses_minute_precision,
    windows_to_grid,
)


def cells_for(day, hours):
    index = DAY_ORDER.index(day)
    return {(index, hour) for hour in hours}


class WindowsToGridTests(unittest.TestCase):
    def test_simple_window_lights_the_hours_it_covers(self):
        windows = [TimeWindow(start="09:00", end="12:00", days=["mon"])]

        self.assertEqual(cells_for("mon", [9, 10, 11]), windows_to_grid(windows))

    def test_partial_end_hour_is_included(self):
        # 09:00-11:45 still occupies part of the 11:00 slot.
        windows = [TimeWindow(start="09:00", end="11:45", days=["mon"])]

        self.assertEqual(cells_for("mon", [9, 10, 11]), windows_to_grid(windows))

    def test_window_spans_every_selected_day(self):
        windows = [TimeWindow(start="09:00", end="11:00", days=["mon", "wed"])]

        expected = cells_for("mon", [9, 10]) | cells_for("wed", [9, 10])
        self.assertEqual(expected, windows_to_grid(windows))

    def test_cross_midnight_window_spills_into_the_next_day(self):
        windows = [TimeWindow(start="22:00", end="02:00", days=["mon"])]

        expected = cells_for("mon", [22, 23]) | cells_for("tue", [0, 1])
        self.assertEqual(expected, windows_to_grid(windows))

    def test_cross_midnight_on_sunday_wraps_to_monday(self):
        windows = [TimeWindow(start="23:00", end="01:00", days=["sun"])]

        expected = cells_for("sun", [23]) | cells_for("mon", [0])
        self.assertEqual(expected, windows_to_grid(windows))

    def test_overlapping_windows_are_merged_by_the_set(self):
        windows = [
            TimeWindow(start="09:00", end="12:00", days=["mon"]),
            TimeWindow(start="11:00", end="14:00", days=["mon"]),
        ]

        self.assertEqual(cells_for("mon", [9, 10, 11, 12, 13]), windows_to_grid(windows))


class GridToWindowsTests(unittest.TestCase):
    def test_contiguous_run_becomes_one_window(self):
        windows = grid_to_windows(cells_for("mon", [9, 10, 11]))

        self.assertEqual(1, len(windows))
        self.assertEqual("09:00", windows[0].start)
        self.assertEqual("12:00", windows[0].end)
        self.assertEqual(["mon"], windows[0].days)

    def test_gap_produces_two_windows(self):
        windows = grid_to_windows(cells_for("mon", [9, 10, 13, 14]))

        self.assertEqual(2, len(windows))
        self.assertEqual(("09:00", "11:00"), (windows[0].start, windows[0].end))
        self.assertEqual(("13:00", "15:00"), (windows[1].start, windows[1].end))

    def test_identical_runs_across_days_collapse_into_one_window(self):
        cells = set()
        for day in ("mon", "tue", "wed", "thu", "fri"):
            cells |= cells_for(day, [9, 10, 11])

        windows = grid_to_windows(cells)

        self.assertEqual(1, len(windows))
        self.assertEqual(["mon", "tue", "wed", "thu", "fri"], windows[0].days)

    def test_days_with_different_runs_stay_separate(self):
        cells = cells_for("mon", [9, 10]) | cells_for("tue", [14, 15])

        windows = grid_to_windows(cells)

        self.assertEqual(2, len(windows))

    def test_full_day_clamps_to_the_last_minute(self):
        windows = grid_to_windows(cells_for("mon", range(24)))

        self.assertEqual(1, len(windows))
        self.assertEqual("00:00", windows[0].start)
        self.assertEqual("23:59", windows[0].end)

    def test_run_reaching_midnight_ends_at_the_last_minute(self):
        windows = grid_to_windows(cells_for("mon", [22, 23]))

        self.assertEqual("22:00", windows[0].start)
        self.assertEqual("23:59", windows[0].end)

    def test_empty_grid_produces_no_windows(self):
        self.assertEqual([], grid_to_windows(set()))

    def test_every_produced_window_is_valid(self):
        cells = set()
        for day_index in range(7):
            for hour in range(24):
                cells.add((day_index, hour))

        for window in grid_to_windows(cells):
            self.assertNotEqual(window.start, window.end)


class RoundTripTests(unittest.TestCase):
    def test_hour_aligned_schedule_survives_a_round_trip(self):
        original = [
            TimeWindow(start="09:00", end="12:00", days=["mon", "tue", "wed", "thu", "fri"]),
            TimeWindow(start="13:00", end="18:00", days=["mon", "tue", "wed", "thu", "fri"]),
        ]

        restored = grid_to_windows(windows_to_grid(original))

        self.assertEqual(2, len(restored))
        self.assertEqual(("09:00", "12:00"), (restored[0].start, restored[0].end))
        self.assertEqual(("13:00", "18:00"), (restored[1].start, restored[1].end))

    def test_round_trip_preserves_when_the_schedule_is_active(self):
        original = ScheduleConfig(
            enabled=True,
            windows=[TimeWindow(start="09:00", end="17:00", days=["wed"])],
        )
        restored = ScheduleConfig(enabled=True, windows=grid_to_windows(windows_to_grid(original.windows)))

        for hour in range(24):
            moment = datetime(2026, 8, 19, hour, 30)  # a Wednesday
            self.assertEqual(
                is_schedule_active(original, moment),
                is_schedule_active(restored, moment),
                "hour {0} disagrees".format(hour),
            )

    def test_cross_midnight_round_trip_keeps_the_same_coverage(self):
        original = [TimeWindow(start="22:00", end="02:00", days=["mon"])]

        restored = grid_to_windows(windows_to_grid(original))
        restored_schedule = ScheduleConfig(enabled=True, windows=restored)

        # Monday 23:30 and Tuesday 01:30 stay covered; Tuesday 03:30 does not.
        self.assertTrue(is_schedule_active(restored_schedule, datetime(2026, 8, 17, 23, 30)))
        self.assertTrue(is_schedule_active(restored_schedule, datetime(2026, 8, 18, 1, 30)))
        self.assertFalse(is_schedule_active(restored_schedule, datetime(2026, 8, 18, 3, 30)))


class MinutePrecisionTests(unittest.TestCase):
    def test_hour_aligned_windows_are_not_flagged(self):
        self.assertFalse(schedule_uses_minute_precision([TimeWindow(start="09:00", end="17:00", days=["mon"])]))

    def test_minute_start_is_flagged(self):
        self.assertTrue(schedule_uses_minute_precision([TimeWindow(start="08:30", end="17:00", days=["mon"])]))

    def test_minute_end_is_flagged(self):
        self.assertTrue(schedule_uses_minute_precision([TimeWindow(start="09:00", end="17:30", days=["mon"])]))

    def test_empty_list_is_not_flagged(self):
        self.assertFalse(schedule_uses_minute_precision([]))


if __name__ == "__main__":
    unittest.main()
