"""Windows-specific paths, DPI, logging, and singleton helpers."""

import ctypes
import faulthandler
import json
import logging
import os
import sys
import tempfile
import threading
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
_fault_log = None

KERNEL32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
KERNEL32.CreateMutexW.restype = ctypes.c_void_p
KERNEL32.CloseHandle.argtypes = (ctypes.c_void_p,)
KERNEL32.CloseHandle.restype = ctypes.c_int


def ensure_app_directories():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


DEFAULT_DPI = 96.0


def enable_dpi_awareness():
    """Opt into real DPI scaling before Tk starts.

    Without this Windows bitmap-stretches the whole window on a scaled display,
    which is what made the control panel look soft on most laptops. Must be
    called before the first Tk window exists.
    """
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2, Windows 10 1703+
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return "per-monitor-v2"
    except (AttributeError, OSError):
        pass

    try:
        # PROCESS_PER_MONITOR_DPI_AWARE, Windows 8.1+
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor"
    except (AttributeError, OSError):
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return "system"
    except (AttributeError, OSError):
        return None


def get_display_scaling():
    """Current UI scale as a multiplier, e.g. 1.5 at 150%."""
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
    except (AttributeError, OSError):
        dpi = 0

    if not dpi:
        try:
            device_context = ctypes.windll.user32.GetDC(None)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(device_context, 88)  # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(None, device_context)
        except (AttributeError, OSError):
            dpi = 0

    if not dpi:
        return 1.0
    return max(1.0, min(3.0, dpi / DEFAULT_DPI))


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


def setup_logging(supervisor=False):
    logger = logging.getLogger("alive_forever.autostart" if supervisor else "alive_forever")
    if logger.handlers:
        return logger


    ensure_app_directories()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = RotatingFileHandler(
        LOG_DIR / ("autostart.log" if supervisor else "alive_forever.log"),
        maxBytes=1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    if not supervisor:
        logging.getLogger("pystray").addHandler(file_handler)

    # A windowed build has no stderr to attach to; adding the handler anyway
    # makes every log call do failing work that logging then swallows.
    if has_console_streams():
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger


def setup_exception_logging(supervisor=False):
    """Install before importing the UI so windowed import failures are recorded."""
    global _fault_log
    logger = setup_logging(supervisor=supervisor)

    def unhandled(exc_type, value, traceback):
        logger.critical("Unhandled application exception", exc_info=(exc_type, value, traceback))

    def thread_unhandled(args):
        if args.exc_type is not SystemExit:
            logger.critical(
                "Unhandled exception in thread %s", args.thread.name if args.thread else "?",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )

    sys.excepthook = unhandled
    threading.excepthook = thread_unhandled
    if _fault_log is None:
        _fault_log = (LOG_DIR / ("autostart_faults.log" if supervisor else "faults.log")).open(
            "a", encoding="utf-8"
        )
        faulthandler.enable(file=_fault_log, all_threads=True)
    return logger


class SingleInstance:
    def __init__(self, mutex_name):
        self.mutex_name = mutex_name
        self.handle = None

    def acquire(self):
        self.handle = KERNEL32.CreateMutexW(None, False, self.mutex_name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return ctypes.get_last_error() != ERROR_ALREADY_EXISTS

    def release(self):
        if self.handle:
            KERNEL32.CloseHandle(self.handle)
            self.handle = None


def show_message_box(message, title=APP_NAME, flags=0):
    return ctypes.windll.user32.MessageBoxW(None, message, title, flags)


def ask_yes_no(message, title=APP_NAME):
    MB_YESNO = 0x04
    MB_ICONQUESTION = 0x20
    IDYES = 6
    return show_message_box(message, title, MB_YESNO | MB_ICONQUESTION) == IDYES