import os
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from alive_forever import app as app_module
from alive_forever.app import KeepAliveApp, build_arg_parser, run_startup_command
from alive_forever.system import startup, windows


class RuntimeFailureTests(unittest.TestCase):
    def setUp(self):
        self.app = KeepAliveApp.__new__(KeepAliveApp)
        self.app.logger = Mock()
        self.app.runtime_failed = threading.Event()
        self.app.shutdown_event = threading.Event()

    def test_worker_exception_requests_failure_exit_and_logs_traceback(self):
        def broken_worker():
            raise RuntimeError("worker failed")

        self.app._run_worker(broken_worker)
        self.assertTrue(self.app.runtime_failed.is_set())
        self.app.logger.exception.assert_called_once()

    def test_unexpected_worker_return_is_a_failure(self):
        self.app._run_worker(lambda: None)
        self.assertTrue(self.app.runtime_failed.is_set())
        self.app.logger.error.assert_called_once()

    def test_worker_return_during_shutdown_is_not_a_failure(self):
        self.app.shutdown_event.set()
        self.app._run_worker(lambda: None)
        self.assertFalse(self.app.runtime_failed.is_set())

    def test_tk_exception_is_logged_and_requests_failure_exit(self):
        error = ValueError("callback failed")
        self.app._report_callback_exception(ValueError, error, None)
        self.assertTrue(self.app.runtime_failed.is_set())
        self.app.logger.error.assert_called_once_with(
            "Unhandled Tk callback exception", exc_info=(ValueError, error, None)
        )

    def test_failure_monitor_quits_on_tk_thread(self):
        self.app.root = Mock()
        self.app.runtime_failed.set()
        self.app._check_runtime()
        self.app.root.quit.assert_called_once()
        self.app.root.after.assert_not_called()

    def test_partial_startup_failure_always_releases_resources(self):
        self.app.instance = Mock()
        self.app.shutdown = Mock()
        self.app._run_session = Mock(side_effect=RuntimeError("Tk failed"))
        with self.assertRaises(RuntimeError):
            self.app.run()
        self.app.shutdown.assert_called_once()

    def test_duplicate_launch_exits_successfully_without_retry(self):
        self.app.instance = Mock()
        self.app.instance.acquire.return_value = False
        with patch.object(app_module, "show_message_box"):
            self.assertEqual(0, self.app.run())
        self.app.instance.release.assert_called_once()

    def test_constructor_failure_is_logged_and_returns_nonzero(self):
        with patch.object(app_module, "KeepAliveApp", side_effect=RuntimeError("config failed")):
            with patch.object(app_module, "has_console_streams", return_value=False):
                with self.assertLogs("alive_forever", level="ERROR"):
                    self.assertEqual(1, app_module.main([]))

    def test_settings_save_keeps_existing_registration(self):
        status = startup.StartupStatus(enabled=True, command=r"C:\Stable\AliveForever.exe")
        with patch.object(startup, "get_startup_status", return_value=status):
            with patch.object(startup, "set_startup_enabled") as register:
                self.assertIs(status, self.app.set_startup_enabled(True))
                register.assert_not_called()

    def test_registration_cli_rejects_unhealthy_result(self):
        with patch.object(startup, "set_startup_enabled", return_value=startup.StartupStatus(
            enabled=True, healthy=False, registration_healthy=False,
        )):
            with patch.object(app_module, "has_console_streams", return_value=False):
                self.assertEqual(1, run_startup_command(build_arg_parser().parse_args(["--register-startup"])))

    def test_registration_cli_does_not_confuse_old_run_failure_with_failed_registration(self):
        with patch.object(startup, "set_startup_enabled", return_value=startup.StartupStatus(
            enabled=True, healthy=False, registration_healthy=True, last_result=1,
        )):
            with patch.object(app_module, "has_console_streams", return_value=False):
                self.assertEqual(0, run_startup_command(build_arg_parser().parse_args(["--register-startup"])))


class ExceptionHookTests(unittest.TestCase):
    def test_entrypoint_import_failure_reaches_persistent_log(self):
        entrypoint = str(Path(__file__).resolve().parents[1] / "keep_alive.py")
        code = """
import builtins
import runpy
original_import = builtins.__import__
def failing_import(name, *args, **kwargs):
    if name == 'alive_forever.app':
        raise RuntimeError('simulated early import failure')
    return original_import(name, *args, **kwargs)
builtins.__import__ = failing_import
runpy.run_path({entrypoint!r}, run_name='__main__')
""".format(entrypoint=entrypoint)
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-c", code], capture_output=True,
                env=dict(os.environ, APPDATA=directory), timeout=30,
            )
            self.assertNotEqual(0, result.returncode)
            log = (Path(directory) / "AliveForever" / "logs" / "alive_forever.log").read_text(
                encoding="utf-8"
            )
            self.assertIn("Unhandled application exception", log)
            self.assertIn("Traceback", log)
            self.assertIn("simulated early import failure", log)

    def test_hooks_record_main_and_background_tracebacks(self):
        old_main, old_thread = sys.excepthook, threading.excepthook
        self.addCleanup(setattr, sys, "excepthook", old_main)
        self.addCleanup(setattr, threading, "excepthook", old_thread)
        logger = Mock()
        with patch.object(windows, "setup_logging", return_value=logger):
            with patch.object(windows, "_fault_log", Mock()):
                windows.setup_exception_logging()
        error = RuntimeError("uncaught")
        sys.excepthook(RuntimeError, error, None)
        threading.excepthook(SimpleNamespace(
            exc_type=RuntimeError, exc_value=error, exc_traceback=None,
            thread=SimpleNamespace(name="background"),
        ))
        self.assertEqual(2, logger.critical.call_count)
        self.assertEqual(
            (RuntimeError, error, None), logger.critical.call_args.kwargs["exc_info"]
        )

    def test_native_fault_capture_is_enabled_with_a_persistent_file(self):
        old_main, old_thread = sys.excepthook, threading.excepthook
        self.addCleanup(setattr, sys, "excepthook", old_main)
        self.addCleanup(setattr, threading, "excepthook", old_thread)
        with patch.object(windows, "_fault_log", None):
            with patch.object(windows.Path, "open") as opened:
                with patch.object(windows.faulthandler, "enable") as enable:
                    windows.setup_exception_logging()
                    enable.assert_called_once_with(file=opened.return_value, all_threads=True)


class SingletonTests(unittest.TestCase):
    def test_mutex_is_pointer_sized_and_released_after_duplicates(self):
        name = "AliveForever.Test.{0}".format(uuid.uuid4())
        first, duplicate, after_release = (windows.SingleInstance(name) for _ in range(3))
        try:
            self.assertTrue(first.acquire())
            self.assertFalse(duplicate.acquire())
            duplicate.release()
            first.release()
            self.assertTrue(after_release.acquire())
        finally:
            first.release()
            duplicate.release()
            after_release.release()


if __name__ == "__main__":
    unittest.main()
