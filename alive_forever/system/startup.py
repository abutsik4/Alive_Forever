"""Windows auto-start registration.

Two mechanisms are supported. A Scheduled Task is preferred because it survives
more environments than the Run key -- users can silently disable Run entries
from Task Manager's Startup tab, and it also lets us delay launch so the app is
not competing with the rest of the boot storm. The Run key remains as a
fallback for machines where task creation is blocked by policy.

Existing registrations are validated without changing which installation owns
them. An autostart supervisor supplies bounded recovery for failed child
processes, even on systems that do not honor Task Scheduler process retries.
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import winreg
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

from alive_forever.system.windows import APP_NAME, ROOT_DIR, STARTUP_KEY


TASK_NAME = APP_NAME
TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
STARTUP_DELAY = "PT30S"
RESTART_COUNT = 3
RESTART_DELAY_SECONDS = 60
AUTOSTART_FLAG = "--autostart"

METHOD_TASK = "task"
METHOD_RUN = "run"

# Keep schtasks from flashing a console window when called from the tray app.
CREATE_NO_WINDOW = 0x08000000


@dataclass
class StartupStatus:
    enabled: bool = False
    method: Optional[str] = None
    command: Optional[str] = None
    arguments: str = ""
    healthy: bool = True
    registration_healthy: bool = True
    detail: str = "Not registered."
    matches_current_copy: bool = True
    recovery_configured: bool = False
    last_result: Optional[int] = None
    task_disabled: bool = False

    def label(self):
        if not self.enabled:
            return "Off"
        if not self.healthy:
            return "Broken"
        return "Task Scheduler" if self.method == METHOD_TASK else "Registry"


def current_user():
    domain = os.environ.get("USERDOMAIN")
    user = os.environ.get("USERNAME") or ""
    return "{0}\\{1}".format(domain, user) if domain and user else user


def launch_target():
    """The (executable, arguments) pair that should start this app."""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve()), ""

    python_path = Path(sys.executable)
    pythonw_path = python_path.with_name("pythonw.exe")
    executable = pythonw_path if pythonw_path.exists() else python_path
    return str(executable.resolve()), str((ROOT_DIR / "keep_alive.py").resolve())


def render_run_command(executable, arguments):
    if arguments:
        return '"{0}" "{1}" {2}'.format(executable, arguments, AUTOSTART_FLAG)
    return '"{0}" {1}'.format(executable, AUTOSTART_FLAG)


def task_arguments(arguments):
    return '"{0}" {1}'.format(arguments, AUTOSTART_FLAG) if arguments else AUTOSTART_FLAG


def without_autostart_flag(arguments):
    text = (arguments or "").strip()
    if text == AUTOSTART_FLAG:
        return ""
    if text.endswith(" " + AUTOSTART_FLAG):
        return text[:-len(AUTOSTART_FLAG)].rstrip()
    return text


def registered_script(method, command, arguments):
    script = without_autostart_flag(arguments)
    if method == METHOD_RUN:
        prefix = '"{0}"'.format(command) if script.startswith('"') else command
        script = script[len(prefix):]
    return script.strip().strip('"')


def supervise_startup(logger):
    """Retry the child ourselves: Windows may treat nonzero exits as completion."""
    executable, script = launch_target()
    command = [executable] + ([script] if script else [])
    for attempt in range(RESTART_COUNT + 1):
        logger.info("Autostart launching application (attempt %s/%s)", attempt + 1, RESTART_COUNT + 1)
        try:
            result = subprocess.run(command, creationflags=CREATE_NO_WINDOW)
            exit_code = result.returncode
        except OSError:
            logger.exception("Could not launch the autostart application")
            exit_code = 1
        if exit_code == 0:
            logger.info("Autostart application exited normally; no retry")
            return 0
        logger.error("Autostart application exited with code %s", exit_code)
        if attempt < RESTART_COUNT:
            logger.warning("Retrying autostart in %s seconds", RESTART_DELAY_SECONDS)
            time.sleep(RESTART_DELAY_SECONDS)
    logger.error("Autostart recovery exhausted after %s attempts", RESTART_COUNT + 1)
    return exit_code


def _run_schtasks(args):
    return subprocess.run(
        ["schtasks"] + args,
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
    )


def _decode_task_xml(raw):
    for encoding in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
        if "<Task" in text:
            return text
    return ""


def build_task_xml(executable, arguments):
    user = current_user()
    user_element = "<UserId>{0}</UserId>".format(_escape(user)) if user else ""
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-16"?>',
            '<Task version="1.2" xmlns="{0}">'.format(TASK_NAMESPACE),
            "  <RegistrationInfo>",
            "    <Description>Starts {0} at logon.</Description>".format(_escape(APP_NAME)),
            "  </RegistrationInfo>",
            "  <Triggers>",
            "    <LogonTrigger>",
            "      <Enabled>true</Enabled>",
            "      <Delay>{0}</Delay>".format(STARTUP_DELAY),
            "      {0}".format(user_element),
            "    </LogonTrigger>",
            "  </Triggers>",
            "  <Principals>",
            '    <Principal id="Author">',
            "      {0}".format(user_element),
            "      <LogonType>InteractiveToken</LogonType>",
            "      <RunLevel>LeastPrivilege</RunLevel>",
            "    </Principal>",
            "  </Principals>",
            "  <Settings>",
            "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>",
            "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>",
            "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>",
            "    <AllowHardTerminate>true</AllowHardTerminate>",
            "    <StartWhenAvailable>true</StartWhenAvailable>",
            "    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>",
            "    <IdleSettings>",
            "      <StopOnIdleEnd>false</StopOnIdleEnd>",
            "      <RestartOnIdle>false</RestartOnIdle>",
            "    </IdleSettings>",
            "    <AllowStartOnDemand>true</AllowStartOnDemand>",
            "    <Enabled>true</Enabled>",
            "    <Hidden>false</Hidden>",
            "    <RunOnlyIfIdle>false</RunOnlyIfIdle>",
            "    <WakeToRun>false</WakeToRun>",
            "    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>",
            "    <Priority>7</Priority>",
            "  </Settings>",
            '  <Actions Context="Author">',
            "    <Exec>",
            "      <Command>{0}</Command>".format(_escape(executable)),
            "      <Arguments>{0}</Arguments>".format(_escape(task_arguments(arguments))),
            "      <WorkingDirectory>{0}</WorkingDirectory>".format(
                _escape(str(Path(arguments or executable).parent))
            ),
            "    </Exec>",
            "  </Actions>",
            "</Task>",
        ]
    )


def _escape(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def parse_task_action(task_xml):
    """Pull (command, arguments) out of a task definition, or (None, '') if absent."""
    try:
        root = ElementTree.fromstring(task_xml)
    except ElementTree.ParseError:
        return None, ""

    namespace = {"t": TASK_NAMESPACE}
    exec_node = root.find(".//t:Actions/t:Exec", namespace)
    if exec_node is None:
        exec_node = root.find(".//Actions/Exec")
        if exec_node is None:
            return None, ""
        command_node = exec_node.find("Command")
        arguments_node = exec_node.find("Arguments")
    else:
        command_node = exec_node.find("t:Command", namespace)
        arguments_node = exec_node.find("t:Arguments", namespace)

    command = (command_node.text or "").strip() if command_node is not None else None
    arguments = (arguments_node.text or "").strip() if arguments_node is not None else ""
    return command or None, arguments


def read_task_registration():
    try:
        result = _run_schtasks(["/Query", "/TN", TASK_NAME, "/XML", "ONE"])
    except OSError:
        return None
    if result.returncode != 0:
        return None

    task_xml = _decode_task_xml(result.stdout or b"")
    if not task_xml:
        return None
    return parse_task_action(task_xml)


def read_run_registration():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return value
    except OSError:
        return None


def _executable_from_run_value(value):
    """First token of a Run value, honouring the quoting we wrote it with."""
    text = (value or "").strip()
    if not text:
        return ""
    if text.startswith('"'):
        closing = text.find('"', 1)
        return text[1:closing] if closing > 0 else text[1:]
    return text.split(" ", 1)[0]


def get_startup_status():
    """Report whether auto-start is registered, how, and whether it still resolves."""
    expected_exe, expected_args = launch_target()

    task_registration = read_task_registration()
    if task_registration is not None:
        command, arguments = task_registration
        status = _evaluate(METHOD_TASK, command, arguments, expected_exe, expected_args)
        try:
            runtime = read_task_runtime()
        except (OSError, ValueError, subprocess.SubprocessError):
            logging.getLogger("alive_forever").exception("Could not inspect startup task runtime")
            status.healthy = False
            status.registration_healthy = False
            status.detail += " Could not read task execution status; see the log."
            return status
        status.recovery_configured = (
            runtime["restart_count"] == 0
            and arguments.strip().endswith(AUTOSTART_FLAG)
        )
        status.last_result = runtime["last_result"]
        if runtime["state"] == "Disabled":
            status.task_disabled = True
            status.healthy = False
            status.registration_healthy = False
            status.detail += " The logon task is disabled."
        elif runtime["state"] != "Running" and status.last_result not in (0, 0x41303):
            status.healthy = False
            status.detail += " Last task execution failed (0x{0:08X}). See the log.".format(
                status.last_result & 0xFFFFFFFF
            )
        elif runtime["state"] == "Running":
            status.detail += " The task is running."
        if not status.recovery_configured:
            status.healthy = False
            status.registration_healthy = False
            status.detail += " Automatic failure recovery is not configured."
        return status

    run_value = read_run_registration()
    if run_value is not None:
        command = _executable_from_run_value(run_value)
        arguments = run_value
        status = _evaluate(METHOD_RUN, command, arguments, expected_exe, expected_args)
        status.recovery_configured = arguments.strip().endswith(AUTOSTART_FLAG)
        return status

    return StartupStatus(enabled=False, detail="Alive Forever will not start on its own.")


def read_task_runtime():
    # Structured output avoids parsing schtasks' localized status text.
    script = (
        "$ErrorActionPreference='Stop'; "
        "$t=Get-ScheduledTask -TaskName 'Alive Forever' -TaskPath '\\'; "
        "$i=$t | Get-ScheduledTaskInfo; "
        "@{state=[string]$t.State; last_result=[long]$i.LastTaskResult; "
        "restart_count=[int]$t.Settings.RestartCount; "
        "restart_interval=[string]$t.Settings.RestartInterval} | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=20, check=True,
    )
    runtime = json.loads(result.stdout)
    if (
        not isinstance(runtime, dict)
        or not isinstance(runtime.get("state"), str)
        or not isinstance(runtime.get("last_result"), int)
        or not isinstance(runtime.get("restart_count"), int)
        or not isinstance(runtime.get("restart_interval"), str)
    ):
        raise ValueError("Invalid task runtime response")
    return runtime


def _evaluate(method, command, arguments, expected_exe, expected_args):
    status = StartupStatus(enabled=True, method=method, command=command, arguments=arguments)

    if not command or not Path(command).exists():
        status.healthy = False
        status.registration_healthy = False
        status.detail = "Registered, but the program it points at is missing: {0}".format(command or "?")
        return status

    script = registered_script(method, command, arguments)
    if script and not Path(script).is_file():
        status.healthy = False
        status.registration_healthy = False
        status.detail = "Registered, but the startup script is missing: {0}".format(script)
        return status

    status.matches_current_copy = (
        os.path.normcase(str(Path(command))) == os.path.normcase(expected_exe)
        and os.path.normcase(script) == os.path.normcase(expected_args)
    )
    status.detail = "Alive Forever starts automatically at logon."
    if not status.matches_current_copy:
        status.detail += " Uses another registered copy; launching this copy will not replace it."
    return status


def enable_task_startup(executable, arguments, logger):
    task_xml = build_task_xml(executable, arguments)
    handle_fd, temp_name = tempfile.mkstemp(suffix=".xml", prefix="alive_forever_task")
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-16") as handle:
            handle.write(task_xml)
        result = _run_schtasks(["/Create", "/TN", TASK_NAME, "/XML", temp_name, "/F"])
    except OSError:
        logger.exception("Could not invoke schtasks")
        return False
    finally:
        try:
            os.unlink(temp_name)
        except OSError:
            pass

    if result.returncode != 0:
        logger.warning(
            "schtasks refused to create the logon task (exit %s): %s",
            result.returncode,
            _decode_task_xml(result.stderr or b"") or (result.stderr or b"").decode("utf-8", "replace").strip(),
        )
        return False

    logger.info("Registered logon task '%s'", TASK_NAME)
    return True


def disable_task_startup(logger):
    try:
        result = _run_schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
    except OSError:
        logger.exception("Could not invoke schtasks")
        return False
    if result.returncode == 0:
        logger.info("Removed logon task '%s'", TASK_NAME)
        return True
    return False


def enable_run_startup(executable, arguments, logger):
    command = render_run_command(executable, arguments)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
    logger.info("Registered Run key startup entry")
    return True


def disable_run_startup(logger):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
        logger.info("Removed Run key startup entry")
        return True
    except FileNotFoundError:
        return True
    except OSError:
        logger.exception("Could not remove Run key startup entry")
        return False


def set_startup_enabled(enabled, logger):
    """Register or clear auto-start, preferring a logon task over the Run key."""
    executable, arguments = launch_target()

    if not enabled:
        disable_task_startup(logger)
        if not disable_run_startup(logger):
            raise RuntimeError("Could not remove the Windows startup entry.")
        return get_startup_status()

    if enable_task_startup(executable, arguments, logger):
        # Only one mechanism should be live, or the app would be launched twice.
        disable_run_startup(logger)
        return get_startup_status()

    logger.info("Falling back to the Run key for startup registration")
    try:
        enable_run_startup(executable, arguments, logger)
    except OSError as error:
        raise RuntimeError("Could not modify startup settings: {0}".format(error))
    return get_startup_status()


def repair_startup_if_stale(logger):
    """Upgrade our recovery policy without taking ownership from another copy."""
    status = get_startup_status()
    executable, arguments = launch_target()
    registered_arguments = registered_script(status.method, status.command, status.arguments)
    owns_registration = (
        status.method in (METHOD_TASK, METHOD_RUN)
        and os.path.normcase(status.command or "") == os.path.normcase(executable)
        and os.path.normcase(registered_arguments) == os.path.normcase(arguments)
    )
    if not owns_registration or status.recovery_configured or status.task_disabled:
        return status
    if status.method == METHOD_TASK and status.last_result is None:
        logger.warning("Leaving startup unchanged because task execution status is unavailable")
        return status

    logger.info("Upgrading this copy's startup recovery policy")
    try:
        return set_startup_enabled(True, logger)
    except RuntimeError:
        logger.exception("Could not repair the startup registration")
        return status
