import unittest

from alive_forever.ui.settings import SettingsWindow


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


if __name__ == "__main__":
    unittest.main()