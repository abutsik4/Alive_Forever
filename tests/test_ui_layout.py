import unittest

from alive_forever.ui.settings import ModernStyle, SettingsWindow


class SettingsWindowLayoutTests(unittest.TestCase):
    def test_geometry_uses_full_size_on_large_screens(self):
        self.assertEqual((620, 860, 650, 110), SettingsWindow.calculate_window_geometry(1920, 1080))

    def test_geometry_clamps_height_on_scaled_laptop_screen(self):
        width, height, x_pos, y_pos = SettingsWindow.calculate_window_geometry(1366, 768)

        self.assertEqual(620, width)
        self.assertEqual(688, height)
        self.assertEqual(373, x_pos)
        self.assertEqual(40, y_pos)

    def test_geometry_never_exceeds_small_screen_height(self):
        width, height, x_pos, y_pos = SettingsWindow.calculate_window_geometry(1024, 600)

        self.assertEqual(620, width)
        self.assertEqual(520, height)
        self.assertEqual(202, x_pos)
        self.assertEqual(40, y_pos)


class ScaledGeometryTests(unittest.TestCase):
    """With DPI awareness on, screen dimensions arrive in physical pixels."""

    def test_window_grows_with_the_display_scale(self):
        # A 1920x1080 logical display at 150% reports 2880x1620.
        width, height, _, _ = SettingsWindow.calculate_window_geometry(2880, 1620, scale=1.5)

        self.assertEqual(930, width)
        self.assertEqual(1290, height)

    def test_scaled_window_still_fits_a_short_screen(self):
        width, height, _, y_pos = SettingsWindow.calculate_window_geometry(2048, 1152, scale=1.5)

        self.assertEqual(930, width)
        self.assertEqual(1072, height)
        self.assertLessEqual(height, 1152)
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


if __name__ == "__main__":
    unittest.main()