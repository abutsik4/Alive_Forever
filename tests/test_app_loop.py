import threading
import unittest

from alive_forever.app import KeepAliveApp
from alive_forever.core.config import AppConfig


class KeepAliveAppLoopTests(unittest.TestCase):
    def _build_app(self, **config_overrides):
        settings = {"interval": 60, "idle_aware": False, "prevent_sleep": False, "keep_display_on": False}
        settings.update(config_overrides)

        app = KeepAliveApp.__new__(KeepAliveApp)
        app.config = AppConfig(**settings)
        app.config_lock = threading.RLock()
        app.shutdown_event = threading.Event()
        app.sync_execution_state = lambda: False
        return app

    def test_process_activity_tick_skips_when_state_turns_off_before_simulate(self):
        app = self._build_app()
        states = iter(["active", "scheduled_off"])
        app.get_runtime_state = lambda now=None: next(states)
        app.refresh_runtime_state = lambda notify=True: None
        app.simulate_activity = lambda: self.fail("simulate_activity should not run when schedule turned off")

        next_run = KeepAliveApp.process_activity_tick(app, 100.0, now_monotonic=100.0)

        self.assertEqual(100.0, next_run)

    def test_process_activity_tick_runs_when_state_stays_active(self):
        app = self._build_app()
        app.get_runtime_state = lambda now=None: "active"
        app.refresh_runtime_state = lambda notify=True: None
        activity_calls = []
        app.simulate_activity = lambda: activity_calls.append("called")

        next_run = KeepAliveApp.process_activity_tick(app, 100.0, now_monotonic=100.0)

        self.assertEqual(["called"], activity_calls)
        self.assertEqual(160.0, next_run)


class IdleAwareInjectionTests(unittest.TestCase):
    """With idle awareness on we must not fight the user for their own keyboard."""

    def _build_app(self, idle_seconds, threshold=45):
        app = KeepAliveApp.__new__(KeepAliveApp)
        app.config = AppConfig(interval=60, idle_aware=True, idle_threshold=threshold)
        app.config_lock = threading.RLock()
        app.shutdown_event = threading.Event()
        app.logger = type("L", (), {"debug": lambda *a, **k: None})()
        app.get_runtime_state = lambda now=None: "active"
        app.refresh_runtime_state = lambda notify=True: None
        app.sync_execution_state = lambda: False
        app.injections = []
        app.simulate_activity = lambda: app.injections.append("injected")

        import alive_forever.app as app_module

        original = app_module.presence.get_idle_seconds
        app_module.presence.get_idle_seconds = lambda: idle_seconds
        self.addCleanup(lambda: setattr(app_module.presence, "get_idle_seconds", original))
        return app

    def test_no_injection_while_the_user_is_at_the_keyboard(self):
        app = self._build_app(idle_seconds=3.0)

        next_run = KeepAliveApp.process_activity_tick(app, 100.0, now_monotonic=100.0)

        self.assertEqual([], app.injections)
        # Retries soon rather than burning a whole interval.
        self.assertEqual(115.0, next_run)

    def test_injection_once_the_user_has_been_away_long_enough(self):
        app = self._build_app(idle_seconds=90.0)

        next_run = KeepAliveApp.process_activity_tick(app, 100.0, now_monotonic=100.0)

        self.assertEqual(["injected"], app.injections)
        self.assertEqual(160.0, next_run)

    def test_threshold_boundary_counts_as_away(self):
        app = self._build_app(idle_seconds=45.0, threshold=45)

        KeepAliveApp.process_activity_tick(app, 100.0, now_monotonic=100.0)

        self.assertEqual(["injected"], app.injections)

    def test_should_inject_returns_the_observed_idle_time(self):
        app = self._build_app(idle_seconds=12.5)

        should_inject, idle_seconds = app.should_inject_now()

        self.assertFalse(should_inject)
        self.assertEqual(12.5, idle_seconds)

    def test_idle_awareness_disabled_always_injects(self):
        app = self._build_app(idle_seconds=0.0)
        app.config.idle_aware = False

        should_inject, _ = app.should_inject_now()

        self.assertTrue(should_inject)


if __name__ == "__main__":
    unittest.main()
