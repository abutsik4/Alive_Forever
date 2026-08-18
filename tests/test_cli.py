import contextlib
import io
import threading
import unittest

from alive_forever.app import KeepAliveApp, build_arg_parser
from alive_forever.core.config import AppConfig


class ArgParsingTests(unittest.TestCase):
    def setUp(self):
        self.parser = build_arg_parser()

    def test_no_arguments_selects_normal_startup(self):
        args = self.parser.parse_args([])

        self.assertFalse(args.register_startup)
        self.assertFalse(args.unregister_startup)
        self.assertFalse(args.startup_status)
        self.assertFalse(args.paused)
        self.assertFalse(args.minimized)
        self.assertIsNone(args.preset)

    def test_installer_flags(self):
        self.assertTrue(self.parser.parse_args(["--register-startup"]).register_startup)
        self.assertTrue(self.parser.parse_args(["--unregister-startup"]).unregister_startup)
        self.assertTrue(self.parser.parse_args(["--startup-status"]).startup_status)

    def test_launch_flags(self):
        args = self.parser.parse_args(["--paused", "--minimized"])

        self.assertTrue(args.paused)
        self.assertTrue(args.minimized)

    def test_preset_accepts_a_known_name(self):
        self.assertEqual("Workday", self.parser.parse_args(["--preset", "Workday"]).preset)

    def test_preset_rejects_an_unknown_name(self):
        # argparse writes its usage to stderr on failure; swallow it so the
        # test run stays readable.
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.parser.parse_args(["--preset", "Nonsense"])

    def test_unknown_flag_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.parser.parse_args(["--definitely-not-a-flag"])


class LaunchOptionTests(unittest.TestCase):
    def _build_app(self):
        app = KeepAliveApp.__new__(KeepAliveApp)
        app.config = AppConfig()
        app.config_lock = threading.RLock()
        app.manual_paused = False
        app.start_minimized_override = False
        app.saves = []
        app.save_config = lambda: app.saves.append("saved")
        app.logger = type("L", (), {"info": lambda *a, **k: None, "exception": lambda *a, **k: None})()
        return app

    def test_paused_flag_starts_paused(self):
        app = self._build_app()

        app.apply_launch_options(build_arg_parser().parse_args(["--paused"]))

        self.assertTrue(app.manual_paused)

    def test_paused_flag_is_not_persisted(self):
        # A one-off launch option must not permanently pause the app.
        app = self._build_app()

        app.apply_launch_options(build_arg_parser().parse_args(["--paused"]))

        self.assertEqual([], app.saves)

    def test_minimized_flag_sets_the_session_override(self):
        app = self._build_app()
        app.config.start_minimized = False

        app.apply_launch_options(build_arg_parser().parse_args(["--minimized"]))

        self.assertTrue(app.start_minimized_override)
        self.assertFalse(app.config.start_minimized)

    def test_preset_flag_applies_and_persists(self):
        app = self._build_app()

        app.apply_launch_options(build_arg_parser().parse_args(["--preset", "Workday"]))

        self.assertEqual("Workday", app.config.profile_name)
        self.assertTrue(app.config.schedule.enabled)
        self.assertEqual(["saved"], app.saves)

    def test_no_flags_changes_nothing(self):
        app = self._build_app()

        app.apply_launch_options(build_arg_parser().parse_args([]))

        self.assertFalse(app.manual_paused)
        self.assertFalse(app.start_minimized_override)
        self.assertEqual("Custom", app.config.profile_name)
        self.assertEqual([], app.saves)

    def test_a_failing_save_does_not_abort_the_launch(self):
        app = self._build_app()

        def _boom():
            raise OSError("read-only")

        app.save_config = _boom

        app.apply_launch_options(build_arg_parser().parse_args(["--preset", "Evening"]))

        self.assertEqual("Evening", app.config.profile_name)


if __name__ == "__main__":
    unittest.main()
