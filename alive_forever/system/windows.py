"""Windows-specific paths, startup registration, logging, and singleton helpers."""

import ctypes
import json
import logging
import os
import sys
import tempfile
import winreg
from logging.handlers import RotatingFileHandler
from pathlib import Path


# Bind kernel32 with use_last_error so GetLastError() reflects the call we just
# made rather than whatever the ctypes/CRT machinery did in between.
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)

APP_NAME = "Alive Forever"
APP_FOLDER_NAME = "AliveForever"
APP_DIR = Path(os.getenv("APPDATA") or Path.cwd()) / APP_FOLDER_NAME
LOG_DIR = APP_DIR / "logs"
CONFIG_FILE = APP_DIR / "config.json"
ROOT_DIR = Path(__file__).resolve().parents[2]
LEGACY_CONFIG_FILE = ROOT_DIR / "config.json"
ICON_FILE = ROOT_DIR / "icon.png"
ICO_FILE = ROOT_DIR / "icon.ico"
STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
MUTEX_NAME = "AliveForever.Singleton"
ERROR_ALREADY_EXISTS = 183


def ensure_app_directories():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def has_console_streams():
    """False in pythonw/windowed PyInstaller builds, where stdio is None."""
    return sys.stderr is not None and sys.stdout is not None


def write_json_atomic(path, payload):
    """Write JSON via a temp file + os.replace so a crash can't truncate the target."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    handle_fd, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def setup_logging():
    logger = logging.getLogger("alive_forever")
    if logger.handlers:
        return logger

    ensure_app_directories()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = RotatingFileHandler(
        LOG_DIR / "alive_forever.log",
        maxBytes=1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # A windowed build has no stderr to attach to; adding the handler anyway
    # makes every log call do failing work that logging then swallows.
    if has_console_streams():
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger


class SingleInstance:
    def __init__(self, mutex_name):
        self.mutex_name = mutex_name
        self.handle = None

    def acquire(self):
        self.handle = KERNEL32.CreateMutexW(None, False, self.mutex_name)
        return ctypes.get_last_error() != ERROR_ALREADY_EXISTS

    def release(self):
        if self.handle:
            KERNEL32.CloseHandle(self.handle)
            self.handle = None


def build_startup_command(script_path):
    if getattr(sys, "frozen", False):
        return '"{0}"'.format(sys.executable)

    python_path = Path(sys.executable)
    pythonw_path = python_path.with_name("pythonw.exe")
    executable = pythonw_path if pythonw_path.exists() else python_path
    return '"{0}" "{1}"'.format(executable, script_path)


def is_startup_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except OSError:
        return False


def set_startup_enabled(enabled, startup_command, logger):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command)
            logger.info("Enabled startup registration")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
            logger.info("Disabled startup registration")
        winreg.CloseKey(key)
    except Exception as error:
        logger.exception("Could not update startup registration")
        raise RuntimeError("Could not modify startup settings: {0}".format(error))


def show_message_box(message, title=APP_NAME):
    ctypes.windll.user32.MessageBoxW(None, message, title, 0)