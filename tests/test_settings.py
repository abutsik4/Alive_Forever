import tkinter as tk
import unittest

from alive_forever.core.scheduler import DAY_ORDER, TimeWindow
from alive_forever.ui.settings import SettingsWindow


class _ListboxStub:
    def __init__(self, selection):
        self._selection = selection

    def curselection(self):
        return self._selection


class SettingsWindowSaveTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tcl()

    def _build_window(self, selection=(0,), start="10:00", end="18:00", selected_days=None):
        if selected_days is None:
            selected_days = ["mon"]

        window = SettingsWindow.__new__(SettingsWindow)
        window.draft_windows = [TimeWindow(start="09:00", end="17:00", days=["mon"])]
        window.window_start_var = tk.StringVar(master=self.root, value=start)
        window.window_end_var = tk.StringVar(master=self.root, value=end)
        window.window_day_vars = {
            day: tk.BooleanVar(master=self.root, value=day in selected_days) for day in DAY_ORDER
        }
        window.windows_listbox = _ListboxStub(selection)
        return window

    def test_build_schedule_windows_for_save_updates_selected_window(self):
        window = self._build_window(selection=(0,), start="10:00", end="18:00", selected_days=["mon", "wed"])

        schedule_windows = window.build_schedule_windows_for_save()

        self.assertEqual(1, len(schedule_windows))
        self.assertEqual("10:00", schedule_windows[0].start)
        self.assertEqual("18:00", schedule_windows[0].end)
        self.assertEqual(["mon", "wed"], schedule_windows[0].days)

    def test_build_schedule_windows_for_save_keeps_draft_without_selection(self):
        window = self._build_window(selection=(), start="10:00", end="18:00", selected_days=["mon", "wed"])

        schedule_windows = window.build_schedule_windows_for_save()

        self.assertEqual(1, len(schedule_windows))
        self.assertEqual("09:00", schedule_windows[0].start)
        self.assertEqual("17:00", schedule_windows[0].end)
        self.assertEqual(["mon"], schedule_windows[0].days)

    def test_untouched_editor_adds_nothing(self):
        window = self._build_window(selection=(), start="09:00", end="17:00", selected_days=["mon"])

        self.assertEqual(1, len(window.build_schedule_windows_for_save()))

    def test_dirty_editor_without_selection_is_committed_instead_of_discarded(self):
        window = self._build_window(selection=(), start="19:00", end="22:00", selected_days=["sat", "sun"])
        window._editor_dirty = True

        schedule_windows = window.build_schedule_windows_for_save()

        self.assertEqual(2, len(schedule_windows))
        self.assertEqual("09:00", schedule_windows[0].start)
        self.assertEqual("19:00", schedule_windows[1].start)
        self.assertEqual("22:00", schedule_windows[1].end)
        self.assertEqual(["sat", "sun"], schedule_windows[1].days)

    def test_dirty_editor_matching_an_existing_window_is_not_duplicated(self):
        window = self._build_window(selection=(), start="09:00", end="17:00", selected_days=["mon"])
        window._editor_dirty = True

        schedule_windows = window.build_schedule_windows_for_save()

        self.assertEqual(1, len(schedule_windows))

    def test_dirty_editor_with_no_days_selected_raises(self):
        window = self._build_window(selection=(), start="19:00", end="22:00", selected_days=[])
        window._editor_dirty = True

        with self.assertRaises(ValueError):
            window.build_schedule_windows_for_save()


if __name__ == "__main__":
    unittest.main()