import unittest
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import Mock, patch

from alive_forever.core.config import AppConfig
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


class ExactTimeTests(unittest.TestCase):
    def test_accepts_quarter_hours_and_arbitrary_minutes(self):
        for end in ("16:15", "16:30", "16:37"):
            window = SettingsWindow.make_time_window(" 9:05 ", end, ["mon", "fri"])
            self.assertEqual("09:05", window.start)
            self.assertEqual(end, window.end)
            self.assertEqual(["mon", "fri"], window.days)

    def test_rejects_invalid_times_and_empty_days(self):
        for start, end, days in (
            ("24:00", "16:30", ["mon"]), ("09:00", "16:60", ["mon"]),
            ("bad", "16:30", ["mon"]), ("16:30", "16:30", ["mon"]),
            ("09:00", "16:30", []),
        ):
            with self.subTest(start=start, end=end, days=days), self.assertRaises(ValueError):
                SettingsWindow.make_time_window(start, end, days)

    def test_accepts_overnight_window(self):
        window = SettingsWindow.make_time_window("22:15", "01:30", ["sun"])
        self.assertEqual(("22:15", "01:30"), (window.start, window.end))


class ScheduleEditorUITests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = SimpleNamespace(config=AppConfig(), logger=Mock())
        self.app.config.schedule.enabled = True
        self.window = SettingsWindow(self.app)
        self.window.window = self.root
        self.window.draft_windows = [TimeWindow("09:00", "16:00", ["mon"])]
        self.window.grid_cells = windows_to_grid(self.window.draft_windows)
        self.frame = tk.Frame(self.root)
        self.frame.pack()
        self.window._build_schedule_tab(self.frame)

    def widgets(self, parent, cls):
        result = []
        for child in parent.winfo_children():
            if isinstance(child, cls):
                result.append(child)
            result.extend(self.widgets(child, cls))
        return result

    def button(self, parent, text):
        return next(button for button in self.widgets(parent, tk.Button) if button.cget("text") == text)

    def test_edit_exact_window_updates_draft_and_grid_without_rounding(self):
        from tkinter import ttk

        manager = self.window._edit_exact_times()
        listing = self.widgets(manager, tk.Listbox)[0]
        listing.selection_set(0)
        self.button(manager, "Edit").invoke()
        editor = self.widgets(manager, tk.Toplevel)[0]
        combos = self.widgets(editor, ttk.Combobox)
        combos[0].set("09:15")
        combos[1].set("16:37")
        self.button(editor, "Save window").invoke()
        saved = self.window.build_schedule_windows_for_save()
        self.assertEqual(("09:15", "16:37"), (saved[0].start, saved[0].end))
        self.assertIn("16:37", listing.get(0))
        self.assertFalse(self.window._grid_dirty)
        self.assertEqual(windows_to_grid(saved), self.window.grid.cells)
        self.assertIn("Minute-precision", self.window.precision_label.cget("text"))
        self.assertIn("16:37", self.window.schedule_preview_label.cget("text"))
        self.assertEqual("17:00", self.app.config.schedule.windows[0].end)
        self.button(manager, "Done").invoke()

    def test_add_cancel_and_remove_windows(self):
        manager = self.window._edit_exact_times()
        original = self.window.build_schedule_windows_for_save()
        self.button(manager, "Add").invoke()
        editor = self.widgets(manager, tk.Toplevel)[0]
        self.button(editor, "Cancel").invoke()
        self.assertEqual(original, self.window.build_schedule_windows_for_save())
        self.button(manager, "Add").invoke()
        editor = self.widgets(manager, tk.Toplevel)[0]
        self.button(editor, "Save window").invoke()
        self.assertEqual(2, len(self.window.build_schedule_windows_for_save()))
        listing = self.widgets(manager, tk.Listbox)[0]
        listing.selection_set(0)
        self.button(manager, "Remove").invoke()
        self.assertEqual(1, len(self.window.build_schedule_windows_for_save()))

    def test_invalid_window_remains_open_and_does_not_change_draft(self):
        from tkinter import ttk

        manager = self.window._edit_exact_times()
        self.button(manager, "Add").invoke()
        editor = self.widgets(manager, tk.Toplevel)[0]
        self.widgets(editor, ttk.Combobox)[1].set("25:00")
        with patch("alive_forever.ui.settings.messagebox.showerror") as error:
            self.button(editor, "Save window").invoke()
        error.assert_called_once()
        self.assertTrue(editor.winfo_exists())
        self.assertEqual(1, len(self.window.build_schedule_windows_for_save()))

    def test_overtime_button_passes_custom_minutes_and_reports_errors(self):
        from datetime import datetime

        self.app.add_overtime = Mock(return_value=datetime(2026, 8, 18, 16, 45))
        dialog = self.window._show_overtime()
        self.window.overtime_var.set("45")
        self.button(dialog, "Add overtime").invoke()
        self.app.add_overtime.assert_called_once_with(45)
        self.assertIn("16:45", self.window._status_message)
        self.window.overtime_var.set("oops")
        with patch("alive_forever.ui.settings.messagebox.showerror") as error:
            self.button(dialog, "Add overtime").invoke()
        error.assert_called_once()
        self.app.add_overtime.assert_called_once()

    def test_saving_settings_applies_exact_minutes(self):
        from datetime import datetime

        self.frame.destroy()
        self.app.is_startup_enabled = Mock(return_value=False)
        self.app.set_startup_enabled = Mock()
        self.app.now_provider = Mock(return_value=datetime(2026, 8, 18, 14))
        self.app.apply_config = Mock(side_effect=lambda config: setattr(self.app, "config", config))
        self.window._create_ui()
        self.window._set_exact_windows([TimeWindow("09:15", "16:30", ["mon", "fri"])])
        self.window._save_settings()
        self.app.apply_config.assert_called_once()
        self.assertEqual("16:30", self.app.config.schedule.windows[0].end)
        self.assertEqual("09:15", self.app.config.schedule.windows[0].start)
        self.assertEqual(["mon", "fri"], self.app.config.schedule.windows[0].days)
        self.assertIn("Settings saved", self.window._status_message)

    def test_new_controls_fit_minimum_settings_height(self):
        self.frame.destroy()
        self.app.is_startup_enabled = Mock(return_value=False)
        self.window._create_ui()
        self.window._select_tab("Schedule")
        self.window._set_exact_windows([TimeWindow("09:15", "16:30", DAY_ORDER[:5])])
        self.root.geometry("640x460+0+0")
        self.root.deiconify()
        self.root.update()
        for widget in (self.window.schedule_preview_label, self.window.status_bar,
                       self.button(self.root, "Exact times..."), self.button(self.root, "Overtime...")):
            with self.subTest(widget=widget):
                self.assertTrue(widget.winfo_ismapped())
                self.assertGreaterEqual(widget.winfo_height(), widget.winfo_reqheight())
                self.assertLessEqual(widget.winfo_rooty() - self.root.winfo_rooty() + widget.winfo_height(), 460)


if __name__ == "__main__":
    unittest.main()
