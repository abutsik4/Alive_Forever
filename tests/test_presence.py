import ctypes
import threading
import unittest
from datetime import datetime, timedelta

from alive_forever.app import KeepAliveApp
from alive_forever.core.config import AppConfig, config_from_raw
from alive_forever.core.scheduler import ScheduleConfig, TimeWindow
from alive_forever.system import presence


class Win32StructureTests(unittest.TestCase):
    """A wrong struct layout makes SendInput fail silently, so pin the sizes."""

    def test_input_struct_is_the_size_windows_expects(self):
        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28

        self.assertEqual(expected, ctypes.sizeof(presence.INPUT))

    def test_ulong_ptr_is_pointer_sized(self):
        self.assertEqual(ctypes.sizeof(ctypes.c_void_p), ctypes.sizeof(presence.ULONG_PTR))

    def test_execution_flags_compose_correctly(self):
        self.assertEqual(presence.ES_CONTINUOUS, presence.build_execution_flags(False, False))
        self.assertEqual(
            presence.ES_CONTINUOUS | presence.ES_SYSTEM_REQUIRED,
            presence.build_execution_flags(True, False),
        )
        self.assertEqual(
            presence.ES_CONTINUOUS | presence.ES_SYSTEM_REQUIRED | presence.ES_DISPLAY_REQUIRED,
            presence.build_execution_flags(True, True),
        )
        self.assertEqual(
            presence.ES_CONTINUOUS | presence.ES_DISPLAY_REQUIRED,
            presence.build_execution_flags(False, True),
        )

    def test_idle_seconds_is_never_negative(self):
        self.assertGreaterEqual(presence.get_idle_seconds(), 0.0)


class _App(KeepAliveApp):
    """Constructed without __init__ so nothing touches disk or the tray."""

    def __init__(self, config, now):
        self.config = config
        self.config_lock = threading.RLock()
        self.manual_paused = False
        self._now = now
        self.saved = 0
        self.refreshed = 0
        self._applied_execution_flags = None
        self.logger = type("L", (), {"info": lambda *a, **k: None, "exception": lambda *a, **k: None})()

    def now_provider(self):
        return self._now

    def save_config(self):
        self.saved += 1

    def refresh_runtime_state(self, notify=True):
        self.refreshed += 1


class OverrideTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 18, 14, 0, 0)
        # Schedule that is inactive right now, so overrides are visibly in charge.
        self.schedule = ScheduleConfig(
            enabled=True, windows=[TimeWindow(start="09:00", end="10:00", days=["mon"])]
        )

    def _app(self, **kwargs):
        config = AppConfig(schedule=self.schedule, **kwargs)
        return _App(config, self.now)

    def test_active_override_beats_an_inactive_schedule(self):
        app = self._app(override_state="active", override_until=self.now + timedelta(hours=1))

        self.assertEqual("active", app.get_runtime_state())

    def test_paused_override_beats_an_active_schedule(self):
        app = self._app(override_state="paused", override_until=self.now + timedelta(hours=1))
        app.config.schedule = ScheduleConfig(enabled=False, windows=[])

        self.assertEqual("manual_paused", app.get_runtime_state())

    def test_expired_override_is_ignored(self):
        app = self._app(override_state="active", override_until=self.now - timedelta(seconds=1))

        self.assertIsNone(app.get_active_override())
        self.assertEqual("scheduled_off", app.get_runtime_state())

    def test_override_expiring_exactly_now_is_over(self):
        app = self._app(override_state="active", override_until=self.now)

        self.assertIsNone(app.get_active_override())

    def test_clear_expired_override_wipes_both_fields(self):
        app = self._app(override_state="active", override_until=self.now - timedelta(minutes=5))

        self.assertTrue(app.clear_expired_override())
        self.assertIsNone(app.config.override_state)
        self.assertIsNone(app.config.override_until)

    def test_clear_expired_override_leaves_a_live_override_alone(self):
        app = self._app(override_state="active", override_until=self.now + timedelta(minutes=5))

        self.assertFalse(app.clear_expired_override())
        self.assertEqual("active", app.config.override_state)

    def test_set_override_persists_and_computes_the_deadline(self):
        app = self._app()

        app.set_override("active", 120)

        self.assertEqual("active", app.config.override_state)
        self.assertEqual(self.now + timedelta(minutes=120), app.config.override_until)
        self.assertEqual(1, app.saved)

    def test_setting_an_active_override_lifts_a_manual_pause(self):
        app = self._app()
        app.manual_paused = True

        app.set_override("active", 30)

        self.assertFalse(app.manual_paused)
        self.assertEqual("active", app.get_runtime_state())

    def test_toggle_state_cancels_a_running_override(self):
        app = self._app(override_state="active", override_until=self.now + timedelta(hours=2))

        app.toggle_state()

        self.assertIsNone(app.config.override_state)
        self.assertTrue(app.manual_paused)

    def test_clear_override_resets_to_the_schedule(self):
        app = self._app(override_state="active", override_until=self.now + timedelta(hours=2))

        app.clear_override()

        self.assertIsNone(app.config.override_state)
        self.assertEqual("scheduled_off", app.get_runtime_state())


class ExecutionStateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 18, 14, 0, 0)
        self.applied = []
        self.original = presence.apply_execution_state
        presence.apply_execution_state = lambda *flags: self.applied.append(flags) or True
        self.addCleanup(lambda: setattr(presence, "apply_execution_state", self.original))

    def _app(self, state, **kwargs):
        app = _App(AppConfig(**kwargs), self.now)
        app.get_runtime_state = lambda now=None: state
        return app

    def test_no_hold_is_taken_while_paused(self):
        app = self._app("manual_paused", prevent_sleep=True, keep_display_on=True)

        self.assertEqual((False, False), app.desired_execution_flags())

    def test_no_hold_is_taken_outside_the_schedule(self):
        app = self._app("scheduled_off", prevent_sleep=True)

        self.assertEqual((False, False), app.desired_execution_flags())

    def test_hold_reflects_the_configured_options_while_active(self):
        app = self._app("active", prevent_sleep=True, keep_display_on=True)

        self.assertEqual((True, True), app.desired_execution_flags())

    def test_state_is_applied_once_and_not_re_applied(self):
        app = self._app("active", prevent_sleep=True)

        self.assertTrue(app.sync_execution_state())
        for _ in range(5):
            self.assertFalse(app.sync_execution_state())

        self.assertEqual([(True, False)], self.applied)

    def test_changing_the_desired_state_re_applies(self):
        app = self._app("active", prevent_sleep=True)
        app.sync_execution_state()

        app.config.keep_display_on = True
        self.assertTrue(app.sync_execution_state())

        self.assertEqual([(True, False), (True, True)], self.applied)


class OverrideConfigPersistenceTests(unittest.TestCase):
    def test_override_survives_a_round_trip(self):
        original = AppConfig(
            override_state="active",
            override_until=datetime(2026, 8, 18, 17, 30),
        )

        restored = config_from_raw(original.to_dict())

        self.assertEqual("active", restored.override_state)
        self.assertEqual(datetime(2026, 8, 18, 17, 30), restored.override_until)

    def test_unknown_override_state_is_dropped(self):
        restored = config_from_raw({"override_state": "nonsense", "override_until": "2026-08-18T17:30:00"})

        self.assertIsNone(restored.override_state)
        self.assertIsNone(restored.override_until)

    def test_override_state_without_a_deadline_is_dropped(self):
        restored = config_from_raw({"override_state": "active"})

        self.assertIsNone(restored.override_state)

    def test_keep_awake_defaults(self):
        restored = config_from_raw({})

        self.assertTrue(restored.prevent_sleep)
        self.assertFalse(restored.keep_display_on)
        self.assertTrue(restored.idle_aware)
        self.assertEqual(45, restored.idle_threshold)
        self.assertTrue(restored.zen_jiggle)

    def test_idle_threshold_is_clamped(self):
        self.assertEqual(10, config_from_raw({"idle_threshold": 0}).idle_threshold)
        self.assertEqual(600, config_from_raw({"idle_threshold": 99999}).idle_threshold)
        self.assertEqual(45, config_from_raw({"idle_threshold": "junk"}).idle_threshold)


if __name__ == "__main__":
    unittest.main()
