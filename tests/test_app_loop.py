import threading
import unittest
from types import SimpleNamespace

from alive_forever.app import KeepAliveApp


class KeepAliveAppLoopTests(unittest.TestCase):
    def _build_app(self):
        app = KeepAliveApp.__new__(KeepAliveApp)
        app.config = SimpleNamespace(interval=60)
        app.shutdown_event = threading.Event()
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


if __name__ == "__main__":
    unittest.main()