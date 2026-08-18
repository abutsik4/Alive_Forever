import unittest

from alive_forever.ui.settings import ModernStyle, SettingsWindow


class SettingsWindowLayoutTests(unittest.TestCase):
    def test_geometry_uses_full_size_on_large_screens(self):
        self.assertEqual((640, 580, 640, 250), SettingsWindow.calculate_window_geometry(1920, 1080))

    def test_geometry_fits_a_laptop_screen(self):
        width, height, x_pos, y_pos = SettingsWindow.calculate_window_geometry(1366, 768)

        self.assertEqual(640, width)
        self.assertEqual(580, height)
        self.assertEqual(363, x_pos)
        self.assertEqual(94, y_pos)

    def test_geometry_never_exceeds_small_screen_height(self):
        width, height, x_pos, y_pos = SettingsWindow.calculate_window_geometry(1024, 600)

        self.assertEqual(640, width)
        self.assertEqual(520, height)
        self.assertLessEqual(height, 600)
        self.assertEqual(40, y_pos)

    def test_tabs_removed_the_need_to_scroll(self):
        # The window shrank when the scrolling canvas was replaced by tabs;
        # if it ever grows past a 768px laptop again, the scrollbar is back.
        _, height, _, _ = SettingsWindow.calculate_window_geometry(1366, 768)

        self.assertLessEqual(height, 768 - SettingsWindow.WINDOW_MARGIN)


class ScaledGeometryTests(unittest.TestCase):
    """With DPI awareness on, screen dimensions arrive in physical pixels."""

    def test_window_grows_with_the_display_scale(self):
        # A 1920x1080 logical display at 150% reports 2880x1620.
        width, height, _, _ = SettingsWindow.calculate_window_geometry(2880, 1620, scale=1.5)

        self.assertEqual(960, width)
        self.assertEqual(870, height)

    def test_scaled_window_still_fits_a_short_screen(self):
        width, height, _, y_pos = SettingsWindow.calculate_window_geometry(1536, 864, scale=1.5)

        self.assertEqual(960, width)
        self.assertEqual(784, height)
        self.assertLessEqual(height, 864)
        self.assertGreaterEqual(y_pos, 0)

    def test_scale_of_one_matches_the_unscaled_result(self):
        self.assertEqual(
            SettingsWindow.calculate_window_geometry(1920, 1080),
            SettingsWindow.calculate_window_geometry(1920, 1080, scale=1.0),
        )

    def test_absurd_scales_are_clamped(self):
        self.assertEqual(
            SettingsWindow.calculate_window_geometry(1920, 1080, scale=0.2),
            SettingsWindow.calculate_window_geometry(1920, 1080, scale=1.0),
        )
        self.assertEqual(
            SettingsWindow.calculate_window_geometry(9000, 9000, scale=99.0),
            SettingsWindow.calculate_window_geometry(9000, 9000, scale=3.0),
        )


class ModernStyleScalingTests(unittest.TestCase):
    def setUp(self):
        self.original = ModernStyle.SCALE
        self.addCleanup(lambda: ModernStyle.apply_scaling(self.original))

    def test_scale_is_recorded_and_clamped(self):
        ModernStyle.apply_scaling(1.5)
        self.assertEqual(1.5, ModernStyle.SCALE)

        ModernStyle.apply_scaling(0.1)
        self.assertEqual(1.0, ModernStyle.SCALE)

        ModernStyle.apply_scaling(10.0)
        self.assertEqual(3.0, ModernStyle.SCALE)

    def test_font_point_sizes_are_left_for_tk_to_scale(self):
        ModernStyle.apply_scaling(2.0)

        # Tk already scales point-sized fonts via `tk scaling`; doubling them
        # here as well would apply the display scale twice.
        self.assertEqual(10, ModernStyle.FONT_BODY[1])
        self.assertEqual(18, ModernStyle.FONT_TITLE[1])


class TabTests(unittest.TestCase):
    def test_declared_tabs(self):
        self.assertEqual(("Status", "Activity", "Schedule", "Startup", "About"), SettingsWindow.TABS)


if __name__ == "__main__":
    unittest.main()
