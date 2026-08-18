import unittest

from alive_forever.core.scheduler import DAY_ORDER, TimeWindow, windows_to_grid
from alive_forever.ui.settings import SettingsWindow


class ScheduleSaveTests(unittest.TestCase):
    """The grid only overwrites the saved schedule once the user edits it.

    The grid works in whole hours, so writing it back unconditionally would
    silently round a schedule configured with minute precision.
    """

    def _build_window(self, windows, grid_dirty=False, cells=None):
        window = SettingsWindow.__new__(SettingsWindow)
        window.draft_windows = list(windows)
        window.grid_cells = set(cells) if cells is not None else windows_to_grid(windows)
        window._grid_dirty = grid_dirty
        return window

    def test_untouched_grid_preserves_the_original_windows(self):
        original = [TimeWindow(start="08:30", end="11:45", days=["mon", "tue"])]
        window = self._build_window(original)

        saved = window.build_schedule_windows_for_save()

        self.assertEqual(1, len(saved))
        self.assertEqual("08:30", saved[0].start)
        self.assertEqual("11:45", saved[0].end)
        self.assertEqual(["mon", "tue"], saved[0].days)

    def test_untouched_grid_returns_copies_not_the_originals(self):
        original = [TimeWindow(start="09:00", end="17:00", days=["mon"])]
        window = self._build_window(original)

        saved = window.build_schedule_windows_for_save()
        saved[0].start = "10:00"

        self.assertEqual("09:00", original[0].start)

    def test_edited_grid_replaces_the_windows(self):
        original = [TimeWindow(start="09:00", end="17:00", days=["mon"])]
        monday = DAY_ORDER.index("mon")
        window = self._build_window(
            original,
            grid_dirty=True,
            cells={(monday, hour) for hour in (13, 14, 15)},
        )

        saved = window.build_schedule_windows_for_save()

        self.assertEqual(1, len(saved))
        self.assertEqual("13:00", saved[0].start)
        self.assertEqual("16:00", saved[0].end)
        self.assertEqual(["mon"], saved[0].days)

    def test_clearing_the_grid_yields_no_windows(self):
        original = [TimeWindow(start="09:00", end="17:00", days=["mon"])]
        window = self._build_window(original, grid_dirty=True, cells=set())

        self.assertEqual([], window.build_schedule_windows_for_save())

    def test_edited_grid_merges_days_that_share_a_run(self):
        window = self._build_window(
            [],
            grid_dirty=True,
            cells={(day, hour) for day in range(5) for hour in range(9, 12)},
        )

        saved = window.build_schedule_windows_for_save()

        self.assertEqual(1, len(saved))
        self.assertEqual(["mon", "tue", "wed", "thu", "fri"], saved[0].days)
        self.assertEqual(("09:00", "12:00"), (saved[0].start, saved[0].end))

    def test_hour_aligned_schedule_is_unchanged_by_a_grid_edit_that_restores_it(self):
        original = [TimeWindow(start="09:00", end="12:00", days=["mon"])]
        window = self._build_window(original, grid_dirty=True)

        saved = window.build_schedule_windows_for_save()

        self.assertEqual(("09:00", "12:00"), (saved[0].start, saved[0].end))
        self.assertEqual(["mon"], saved[0].days)

    def test_default_grid_dirty_flag_is_false(self):
        # Guards the class-level default that keeps a partially built window
        # from spuriously overwriting the schedule.
        self.assertFalse(SettingsWindow._grid_dirty)


if __name__ == "__main__":
    unittest.main()
