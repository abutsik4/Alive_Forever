import sys
import unittest
from pathlib import Path

from alive_forever.system import startup


class TaskXmlTests(unittest.TestCase):
    def test_build_and_parse_round_trip(self):
        xml = startup.build_task_xml(r"C:\Program Files\App\AliveForever.exe", "")

        command, arguments = startup.parse_task_action(xml)

        self.assertEqual(r"C:\Program Files\App\AliveForever.exe", command)
        self.assertEqual("", arguments)

    def test_round_trip_preserves_arguments(self):
        xml = startup.build_task_xml(r"C:\Python\pythonw.exe", r"C:\Tools\Alive Forever\keep_alive.py")

        command, arguments = startup.parse_task_action(xml)

        self.assertEqual(r"C:\Python\pythonw.exe", command)
        self.assertEqual(r"C:\Tools\Alive Forever\keep_alive.py", arguments)

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

        self.assertEqual('"C:\\Program Files\\p.exe" "C:\\My Code\\keep_alive.py"', rendered)

    def test_render_run_command_omits_empty_arguments(self):
        self.assertEqual('"C:\\a.exe"', startup.render_run_command(r"C:\a.exe", ""))


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

    def test_existing_executable_pointing_elsewhere_is_unhealthy(self):
        # Real file on disk, but not the copy we would launch.
        status = startup._evaluate(
            startup.METHOD_RUN, self.real_exe, "", r"C:\Other\AliveForever.exe", ""
        )

        self.assertFalse(status.healthy)
        self.assertIn("different copy", status.detail)

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


if __name__ == "__main__":
    unittest.main()
