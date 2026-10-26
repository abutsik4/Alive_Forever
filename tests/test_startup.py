import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from xml.etree import ElementTree

from alive_forever.system import startup


class TaskXmlTests(unittest.TestCase):
    def test_build_and_parse_round_trip(self):
        xml = startup.build_task_xml(r"C:\Program Files\App\AliveForever.exe", "")

        command, arguments = startup.parse_task_action(xml)

        self.assertEqual(r"C:\Program Files\App\AliveForever.exe", command)
        self.assertEqual("--autostart", arguments)

    def test_round_trip_preserves_arguments(self):
        xml = startup.build_task_xml(r"C:\Python\pythonw.exe", r"C:\Tools\Alive Forever\keep_alive.py")

        command, arguments = startup.parse_task_action(xml)

        self.assertEqual(r"C:\Python\pythonw.exe", command)
        self.assertEqual('"C:\\Tools\\Alive Forever\\keep_alive.py" --autostart', arguments)

    def test_task_uses_supervisor_without_unbounded_or_nested_retries(self):
        root = ElementTree.fromstring(startup.build_task_xml(r"C:\Apps\AliveForever.exe", ""))
        ns = {"t": startup.TASK_NAMESPACE}
        self.assertIsNone(root.find("t:Settings/t:RestartOnFailure", namespaces=ns))
        self.assertEqual("--autostart", root.findtext("t:Actions/t:Exec/t:Arguments", namespaces=ns))
        self.assertEqual("PT0S", root.findtext("t:Settings/t:ExecutionTimeLimit", namespaces=ns))

    def test_script_task_has_quoted_path_and_working_directory(self):
        script = r"C:\My Apps\Alive & Forever\keep_alive.py"
        root = ElementTree.fromstring(startup.build_task_xml(r"C:\Python\pythonw.exe", script))
        ns = {"t": startup.TASK_NAMESPACE}
        self.assertEqual('"{0}" --autostart'.format(script), root.findtext("t:Actions/t:Exec/t:Arguments", namespaces=ns))
        self.assertEqual(str(Path(script).parent), root.findtext("t:Actions/t:Exec/t:WorkingDirectory", namespaces=ns))

    def test_ampersands_in_paths_are_escaped_and_recovered(self):
        messy = r"C:\Tools\R&D\alive.exe"

        command, _ = startup.parse_task_action(startup.build_task_xml(messy, ""))

        self.assertEqual(messy, command)

    def test_task_xml_declares_a_logon_trigger_with_a_delay(self):
        xml = startup.build_task_xml("a.exe", "")

        self.assertIn("<LogonTrigger>", xml)
        self.assertIn("<Delay>{0}</Delay>".format(startup.STARTUP_DELAY), xml)

    def test_parse_returns_none_for_garbage(self):
        self.assertEqual((None, ""), startup.parse_task_action("not xml at all"))

    def test_parse_returns_none_when_no_exec_action(self):
        xml = '<?xml version="1.0"?><Task version="1.2"><Actions /></Task>'

        self.assertEqual((None, ""), startup.parse_task_action(xml))


class RunValueTests(unittest.TestCase):
    def test_quoted_executable_with_spaces(self):
        value = '"C:\\Program Files\\Alive\\AliveForever.exe"'

        self.assertEqual(r"C:\Program Files\Alive\AliveForever.exe", startup._executable_from_run_value(value))

    def test_quoted_executable_with_argument(self):
        value = '"C:\\Python\\pythonw.exe" "C:\\Alive\\keep_alive.py"'

        self.assertEqual(r"C:\Python\pythonw.exe", startup._executable_from_run_value(value))

    def test_unquoted_executable(self):
        self.assertEqual(r"C:\alive.exe", startup._executable_from_run_value(r"C:\alive.exe"))

    def test_empty_value(self):
        self.assertEqual("", startup._executable_from_run_value(""))
        self.assertEqual("", startup._executable_from_run_value(None))

    def test_render_run_command_quotes_both_parts(self):
        rendered = startup.render_run_command(r"C:\Program Files\p.exe", r"C:\My Code\keep_alive.py")

        self.assertEqual('"C:\\Program Files\\p.exe" "C:\\My Code\\keep_alive.py" --autostart', rendered)

    def test_render_run_command_omits_empty_arguments(self):
        self.assertEqual('"C:\\a.exe" --autostart', startup.render_run_command(r"C:\a.exe", ""))


class EvaluateTests(unittest.TestCase):
    """A registration is only healthy if it still points at this install."""

    def setUp(self):
        self.real_exe = str(Path(sys.executable).resolve())

    def test_missing_target_is_unhealthy(self):
        status = startup._evaluate(
            startup.METHOD_TASK, r"C:\gone\nothing here.exe", "", self.real_exe, ""
        )

        self.assertTrue(status.enabled)
        self.assertFalse(status.healthy)
        self.assertIn("missing", status.detail)

    def test_empty_command_is_unhealthy(self):
        status = startup._evaluate(startup.METHOD_RUN, "", "", self.real_exe, "")

        self.assertFalse(status.healthy)

    def test_matching_target_is_healthy(self):
        status = startup._evaluate(startup.METHOD_TASK, self.real_exe, "", self.real_exe, "")

        self.assertTrue(status.enabled)
        self.assertTrue(status.healthy)
        self.assertEqual("Task Scheduler", status.label())

    def test_case_differences_still_count_as_matching(self):
        status = startup._evaluate(
            startup.METHOD_TASK, self.real_exe.upper(), "", self.real_exe.lower(), ""
        )

        self.assertTrue(status.healthy)

    def test_existing_executable_pointing_elsewhere_is_preserved(self):
        # Real file on disk, but not the copy we would launch.
        status = startup._evaluate(
            startup.METHOD_RUN, self.real_exe, "", r"C:\Other\AliveForever.exe", ""
        )

        self.assertTrue(status.healthy)
        self.assertFalse(status.matches_current_copy)
        self.assertIn("another registered copy", status.detail)

    def test_script_argument_must_also_match(self):
        status = startup._evaluate(
            startup.METHOD_RUN,
            self.real_exe,
            '"{0}" "C:\\Old\\keep_alive.py"'.format(self.real_exe),
            self.real_exe,
            r"C:\New\keep_alive.py",
        )

        self.assertFalse(status.healthy)

    def test_run_method_label(self):
        status = startup._evaluate(startup.METHOD_RUN, self.real_exe, "", self.real_exe, "")

        self.assertEqual("Registry", status.label())


class StartupStatusTests(unittest.TestCase):
    def test_default_status_is_off(self):
        status = startup.StartupStatus()

        self.assertFalse(status.enabled)
        self.assertEqual("Off", status.label())

    def test_broken_label_wins_over_method(self):
        status = startup.StartupStatus(enabled=True, method=startup.METHOD_TASK, healthy=False)

        self.assertEqual("Broken", status.label())


class LaunchTargetTests(unittest.TestCase):
    def test_source_mode_points_at_keep_alive(self):
        executable, arguments = startup.launch_target()

        self.assertTrue(executable.lower().endswith(("python.exe", "pythonw.exe")))
        self.assertTrue(arguments.endswith("keep_alive.py"))
        self.assertTrue(Path(arguments).exists())


class TaskHealthTests(unittest.TestCase):
    def setUp(self):
        self.exe = str(Path(sys.executable).resolve())
        self.runtime = {
            "state": "Ready", "last_result": 0, "restart_count": 0,
            "restart_interval": "",
        }
        for name, value in (
            ("launch_target", (self.exe, "")),
            ("read_task_registration", (self.exe, "--autostart")),
            ("read_task_runtime", self.runtime),
        ):
            patcher = patch.object(startup, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_failed_last_run_is_not_healthy(self):
        self.runtime["last_result"] = 1
        status = startup.get_startup_status()
        self.assertTrue(status.enabled)
        self.assertFalse(status.healthy)
        self.assertEqual(1, status.last_result)
        self.assertIn("0x00000001", status.detail)

    def test_disabled_task_is_not_healthy(self):
        self.runtime["state"] = "Disabled"
        self.assertFalse(startup.get_startup_status().healthy)

    def test_running_task_is_healthy_despite_previous_error(self):
        self.runtime.update(state="Running", last_result=1)
        status = startup.get_startup_status()
        self.assertTrue(status.healthy)
        self.assertIn("running", status.detail)

    def test_never_run_task_is_not_reported_as_a_failure(self):
        self.runtime["last_result"] = 0x41303
        self.assertTrue(startup.get_startup_status().healthy)

    def test_missing_recovery_policy_is_reported(self):
        self.runtime["restart_count"] = 3
        status = startup.get_startup_status()
        self.assertFalse(status.recovery_configured)
        self.assertIn("not configured", status.detail)

    def test_query_errors_are_logged_and_not_healthy(self):
        with patch.object(startup, "read_task_runtime", side_effect=OSError("query failed")):
            with self.assertLogs("alive_forever", level="ERROR"):
                status = startup.get_startup_status()
        self.assertFalse(status.healthy)


class RegistrationOwnershipTests(unittest.TestCase):
    def test_ordinary_launch_does_not_replace_another_copy_even_if_missing(self):
        status = startup.StartupStatus(
            enabled=True, method=startup.METHOD_TASK, healthy=False,
            command=r"C:\Stable\AliveForever.exe",
        )
        with patch.object(startup, "get_startup_status", return_value=status):
            with patch.object(startup, "set_startup_enabled") as register:
                self.assertIs(status, startup.repair_startup_if_stale(Mock()))
                register.assert_not_called()

    def test_own_legacy_task_is_upgraded(self):
        exe, script = startup.launch_target()
        status = startup.StartupStatus(
            enabled=True, method=startup.METHOD_TASK, command=exe, arguments=script, last_result=0,
        )
        with patch.object(startup, "get_startup_status", return_value=status):
            with patch.object(startup, "set_startup_enabled", return_value=status) as register:
                startup.repair_startup_if_stale(Mock())
                register.assert_called_once()

    def test_own_legacy_run_entry_is_upgraded(self):
        exe, script = startup.launch_target()
        status = startup.StartupStatus(
            enabled=True, method=startup.METHOD_RUN, command=exe,
            arguments='"{0}" "{1}"'.format(exe, script),
        )
        with patch.object(startup, "get_startup_status", return_value=status):
            with patch.object(startup, "set_startup_enabled", return_value=status) as register:
                startup.repair_startup_if_stale(Mock())
                register.assert_called_once()

    def test_runtime_failure_alone_does_not_re_register_task(self):
        exe, script = startup.launch_target()
        status = startup.StartupStatus(
            enabled=True, method=startup.METHOD_TASK, command=exe,
            arguments='"{0}"'.format(script), healthy=False, recovery_configured=True,
        )
        with patch.object(startup, "get_startup_status", return_value=status):
            with patch.object(startup, "set_startup_enabled") as register:
                startup.repair_startup_if_stale(Mock())
                register.assert_not_called()

    def test_disabled_legacy_task_is_not_automatically_reenabled(self):
        exe, script = startup.launch_target()
        status = startup.StartupStatus(
            enabled=True, method=startup.METHOD_TASK, command=exe,
            arguments=script, healthy=False, task_disabled=True,
        )
        with patch.object(startup, "get_startup_status", return_value=status):
            with patch.object(startup, "set_startup_enabled") as register:
                startup.repair_startup_if_stale(Mock())
                register.assert_not_called()


class SupervisorTests(unittest.TestCase):
    def test_successful_exit_is_not_restarted(self):
        with patch.object(startup.subprocess, "run", return_value=Mock(returncode=0)) as run:
            with patch.object(startup.time, "sleep") as sleep:
                self.assertEqual(0, startup.supervise_startup(Mock()))
                self.assertEqual(1, run.call_count)
                sleep.assert_not_called()
                self.assertNotIn("--autostart", run.call_args.args[0])

    def test_failed_child_is_retried_after_exactly_one_minute(self):
        results = [Mock(returncode=1), Mock(returncode=0)]
        with patch.object(startup.subprocess, "run", side_effect=results) as run:
            with patch.object(startup.time, "sleep") as sleep:
                self.assertEqual(0, startup.supervise_startup(Mock()))
                self.assertEqual(2, run.call_count)
                sleep.assert_called_once_with(60)

    def test_retries_are_bounded_to_three_after_the_first_attempt(self):
        logger = Mock()
        with patch.object(startup.subprocess, "run", return_value=Mock(returncode=7)) as run:
            with patch.object(startup.time, "sleep") as sleep:
                self.assertEqual(7, startup.supervise_startup(logger))
                self.assertEqual(4, run.call_count)
                self.assertEqual([((60,),)] * 3, sleep.call_args_list)
                logger.error.assert_any_call("Autostart recovery exhausted after %s attempts", 4)

    def test_launch_failure_is_logged_and_retried(self):
        logger = Mock()
        with patch.object(startup.subprocess, "run", side_effect=[OSError("launch failed"), Mock(returncode=0)]):
            with patch.object(startup.time, "sleep"):
                self.assertEqual(0, startup.supervise_startup(logger))
                logger.exception.assert_called_once()


@unittest.skipUnless(
    os.environ.get("ALIVE_FOREVER_TASK_INTEGRATION") == "1",
    "Opt-in: creates a temporary Windows task and waits for its one-minute retry",
)
class WindowsRetryIntegrationTests(unittest.TestCase):
    def test_windows_retries_failed_process_and_stops_after_success(self):
        name = "AliveForever.RetryTest.{0}".format(uuid.uuid4())
        with tempfile.TemporaryDirectory(prefix="Alive Forever retry ") as directory:
            script = Path(directory) / "retry probe.py"
            launcher = Path(directory) / "supervisor probe.py"
            counter = Path(directory) / "attempts.txt"
            script.write_text(
                "from pathlib import Path\n"
                "counter = Path(__file__).with_name('attempts.txt')\n"
                "attempt = int(counter.read_text()) + 1 if counter.exists() else 1\n"
                "counter.write_text(str(attempt))\n"
                "raise SystemExit(1 if attempt == 1 else 0)\n",
                encoding="utf-8",
            )
            launcher.write_text(
                "import logging, sys\n"
                "sys.path.insert(0, {0!r})\n"
                "from alive_forever.system import startup\n"
                "startup.launch_target = lambda: (sys.executable, {1!r})\n"
                "logger = logging.getLogger('retry_probe')\n"
                "logger.addHandler(logging.NullHandler())\n"
                "raise SystemExit(startup.supervise_startup(logger))\n".format(
                    str(Path(__file__).resolve().parents[1]), str(script)
                ),
                encoding="utf-8",
            )
            xml = Path(directory) / "task.xml"
            definition = ElementTree.fromstring(startup.build_task_xml(sys.executable, str(launcher)))
            tag = "{{{0}}}".format(startup.TASK_NAMESPACE)
            triggers = definition.find(tag + "Triggers")
            triggers.clear()
            trigger = ElementTree.SubElement(triggers, tag + "TimeTrigger")
            ElementTree.SubElement(trigger, tag + "StartBoundary").text = (
                datetime.now() + timedelta(seconds=10)
            ).isoformat(timespec="seconds")
            ElementTree.SubElement(trigger, tag + "Enabled").text = "true"
            xml.write_bytes(ElementTree.tostring(definition, encoding="utf-16", xml_declaration=True))

            def schtasks(*arguments):
                return subprocess.run(
                    ["schtasks.exe", *arguments], capture_output=True,
                    creationflags=startup.CREATE_NO_WINDOW, check=True, timeout=20,
                )

            try:
                schtasks("/Create", "/TN", name, "/XML", str(xml), "/F")
                deadline = time.monotonic() + 100
                while time.monotonic() < deadline:
                    if counter.exists() and counter.read_text() == "2":
                        break
                    time.sleep(1)
                self.assertTrue(counter.exists(), "Windows never launched the probe")
                self.assertEqual("2", counter.read_text(), "Windows did not retry the failed probe")
                time.sleep(5)
                self.assertEqual("2", counter.read_text(), "Successful retry ran more than once")
            finally:
                schtasks("/Delete", "/TN", name, "/F")


if __name__ == "__main__":
    unittest.main()
