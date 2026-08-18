import threading
import unittest
from types import SimpleNamespace

from alive_forever.app import CONFIG_FLUSH_SECONDS, KeepAliveApp


class _IconStub:
    def __init__(self):
        self.icon = None
        self.title = None
        self.icon_assignments = 0
        self.menu_updates = 0

    def __setattr__(self, name, value):
        if name == "icon" and "icon_assignments" in self.__dict__:
            self.__dict__["icon_assignments"] += 1
        object.__setattr__(self, name, value)

    def update_menu(self):
        self.menu_updates += 1


class IconCachingTests(unittest.TestCase):
    def _build_app(self, state="active", title="Alive Forever - Active"):
        app = KeepAliveApp.__new__(KeepAliveApp)
        app.logger = SimpleNamespace(debug=lambda *a, **k: None)
        app._icon_cache = {}
        app._applied_icon_state = None
        app._applied_icon_title = None
        app.icon = _IconStub()
        app._state = state
        app._title = title
        app.get_runtime_state = lambda now=None: app._state
        app.get_tray_title = lambda: app._title
        app.create_icon_image = lambda s: "image-{0}".format(s)
        return app

    def test_icon_image_is_built_once_per_state(self):
        app = self._build_app()
        builds = []
        app.create_icon_image = lambda s: builds.append(s) or "image-{0}".format(s)

        app.get_icon_image("active")
        app.get_icon_image("active")
        app.get_icon_image("scheduled_off")

        self.assertEqual(["active", "scheduled_off"], builds)

    def test_repeated_updates_with_no_change_do_not_touch_the_tray(self):
        app = self._build_app()

        app.update_icon()
        first_assignments = app.icon.icon_assignments
        first_menu_updates = app.icon.menu_updates

        for _ in range(10):
            app.update_icon()

        self.assertEqual(first_assignments, app.icon.icon_assignments)
        self.assertEqual(first_menu_updates, app.icon.menu_updates)

    def test_state_change_reassigns_the_icon(self):
        app = self._build_app()
        app.update_icon()
        before = app.icon.icon_assignments

        app._state = "manual_paused"
        app._title = "Alive Forever - Manually Paused"
        app.update_icon()

        self.assertEqual(before + 1, app.icon.icon_assignments)
        self.assertEqual("image-manual_paused", app.icon.icon)

    def test_title_change_alone_updates_title_without_rebuilding_the_image(self):
        app = self._build_app()
        app.update_icon()
        before = app.icon.icon_assignments

        app._title = "Alive Forever - Active | Next: Scheduled Off at Fri 17:00"
        app.update_icon()

        self.assertEqual(before, app.icon.icon_assignments)
        self.assertEqual(app._title, app.icon.title)


class ConfigFlushTests(unittest.TestCase):
    def _build_app(self):
        app = KeepAliveApp.__new__(KeepAliveApp)
        app.logger = SimpleNamespace(exception=lambda *a, **k: None)
        app.config_lock = threading.RLock()
        app.saves = []
        app.save_config = lambda: app.saves.append("saved")
        return app

    def test_first_tick_only_seeds_the_baseline(self):
        app = self._build_app()

        self.assertFalse(app.flush_config_if_due(1000.0))
        self.assertEqual([], app.saves)

    def test_flush_is_skipped_inside_the_interval(self):
        app = self._build_app()
        app.flush_config_if_due(1000.0)

        self.assertFalse(app.flush_config_if_due(1000.0 + CONFIG_FLUSH_SECONDS - 1))
        self.assertEqual([], app.saves)

    def test_flush_runs_once_the_interval_elapses(self):
        app = self._build_app()
        app.flush_config_if_due(1000.0)
        app._last_flush = 1000.0

        self.assertTrue(app.flush_config_if_due(1000.0 + CONFIG_FLUSH_SECONDS))
        self.assertEqual(["saved"], app.saves)

    def test_a_failing_save_does_not_propagate_or_spin(self):
        app = self._build_app()

        def _boom():
            raise OSError("disk full")

        app.save_config = _boom
        app._last_flush = 1000.0

        self.assertTrue(app.flush_config_if_due(1000.0 + CONFIG_FLUSH_SECONDS))
        # The baseline advanced, so the next tick will not immediately retry.
        self.assertFalse(app.flush_config_if_due(1000.0 + CONFIG_FLUSH_SECONDS + 1))


if __name__ == "__main__":
    unittest.main()
