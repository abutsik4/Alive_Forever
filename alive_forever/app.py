"""Application entrypoint and tray runtime."""

import threading
import time
from datetime import datetime, timedelta

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError as import_error:  # pragma: no cover - depends on the environment
    import ctypes as _ctypes

    _ctypes.windll.user32.MessageBoxW(
        None,
        "Alive Forever needs its dependencies installed.\n\n"
        "Run this from the project folder:\n\n"
        "    pip install -r requirements.txt\n\n"
        "Missing: {0}".format(import_error.name or import_error),
        "Alive Forever",
        0x10,
    )
    raise SystemExit(1)

import tkinter as tk

from alive_forever.core.config import load_app_config, save_app_config
from alive_forever.core.scheduler import format_transition, get_next_transition, is_schedule_active
from alive_forever.system import presence, startup as startup_module
from alive_forever.system.windows import (
    APP_NAME,
    LOG_DIR,
    MUTEX_NAME,
    SingleInstance,
    ask_yes_no,
    enable_dpi_awareness,
    get_display_scaling,
    has_console_streams,
    setup_logging,
    show_message_box,
)
from alive_forever.ui.settings import ModernStyle, SettingsWindow


LOGGER = setup_logging()

# How often the activity loop flushes counters to disk, so a hard kill costs
# at most this much of the lifetime tally.
CONFIG_FLUSH_SECONDS = 120


class KeepAliveApp:
    # Set on the class so the tick path stays safe regardless of how far
    # construction got; __init__ seeds the real baseline.
    _last_flush = None
    _applied_execution_flags = None
    display_scaling = 1.0

    def __init__(self):
        self.logger = LOGGER
        self.config_lock = threading.RLock()
        self.config = load_app_config(self.logger)
        self.manual_paused = False
        self.shutdown_event = threading.Event()
        self.thread = None
        self.icon = None
        self.root = None
        self.settings_window = None
        self.instance = SingleInstance(MUTEX_NAME)

        self.activity_count = 0
        self.start_time = None
        self._last_status = None
        self._shutdown_complete = False
        self._icon_cache = {}
        self._applied_icon_state = None
        self._applied_icon_title = None
        self._last_flush = time.monotonic()
        self._startup_status = None
        self._applied_execution_flags = None

    def now_provider(self):
        return datetime.now()

    def apply_config(self, config):
        with self.config_lock:
            self.config = config
            save_app_config(self.config, self.logger)
        self.refresh_runtime_state(notify=False)

    def save_config(self):
        with self.config_lock:
            save_app_config(self.config, self.logger)
        self._last_flush = time.monotonic()

    def flush_config_if_due(self, now_monotonic=None):
        """Persist counters periodically so a kill or reboot doesn't discard them."""
        current_time = time.monotonic() if now_monotonic is None else now_monotonic
        if self._last_flush is None:
            self._last_flush = current_time
            return False
        if current_time - self._last_flush < CONFIG_FLUSH_SECONDS:
            return False
        try:
            self.save_config()
        except Exception:
            self.logger.exception("Periodic config flush failed")
            self._last_flush = current_time
        return True

    def get_startup_status(self):
        if self._startup_status is None:
            self._startup_status = startup_module.get_startup_status()
        return self._startup_status

    def is_startup_enabled(self):
        return self.get_startup_status().enabled

    def set_startup_enabled(self, enabled):
        self._startup_status = startup_module.set_startup_enabled(enabled, self.logger)
        return self._startup_status

    def repair_startup(self):
        """Re-point a registration left stale by a moved folder or new interpreter."""
        self._startup_status = startup_module.repair_startup_if_stale(self.logger)
        return self._startup_status

    def prompt_first_run(self):
        """Offer to register auto-start once, since nobody finds the checkbox."""
        if self.config.first_run_completed:
            return

        with self.config_lock:
            self.config.first_run_completed = True

        try:
            if not self.get_startup_status().enabled and ask_yes_no(
                "Start {0} automatically when you sign in to Windows?\n\n"
                "You can change this at any time in Settings.".format(APP_NAME),
                APP_NAME,
            ):
                status = self.set_startup_enabled(True)
                self.logger.info("First-run startup registration: %s", status.label())
        except Exception:
            self.logger.exception("First-run startup prompt failed")
        finally:
            try:
                self.save_config()
            except Exception:
                self.logger.exception("Could not record first-run completion")

    def get_active_override(self, now=None):
        """The temporary tray override, if one is set and hasn't expired yet."""
        config = self.config
        if not config.override_state or not config.override_until:
            return None
        if (now or self.now_provider()) >= config.override_until:
            return None
        return config.override_state, config.override_until

    def clear_expired_override(self, now=None):
        config = self.config
        if not config.override_state or not config.override_until:
            return False
        if (now or self.now_provider()) < config.override_until:
            return False

        with self.config_lock:
            self.config.override_state = None
            self.config.override_until = None
        self.logger.info("Temporary override expired")
        return True

    def set_override(self, state, minutes):
        """Hold a state for a fixed number of minutes, e.g. 'active for 2 hours'."""
        until = self.now_provider() + timedelta(minutes=minutes)
        with self.config_lock:
            self.config.override_state = state
            self.config.override_until = until
        if state == "active":
            self.manual_paused = False
        self.logger.info("Override set: %s until %s", state, until.strftime("%a %H:%M"))
        try:
            self.save_config()
        except Exception:
            self.logger.exception("Could not persist override")
        self.refresh_runtime_state()

    def clear_override(self, icon=None, item=None):
        with self.config_lock:
            self.config.override_state = None
            self.config.override_until = None
        self.logger.info("Override cleared")
        try:
            self.save_config()
        except Exception:
            self.logger.exception("Could not persist override")
        self.refresh_runtime_state()

    def get_runtime_state(self, now=None):
        now = now or self.now_provider()

        override = self.get_active_override(now)
        if override:
            return "active" if override[0] == "active" else "manual_paused"

        if self.manual_paused:
            return "manual_paused"
        return "active" if is_schedule_active(self.config.schedule, now=now) else "scheduled_off"

    def should_inject_now(self):
        """Skip injection while the user is actually at the machine."""
        if not self.config.idle_aware:
            return True, 0.0
        idle_seconds = presence.get_idle_seconds()
        return idle_seconds >= self.config.idle_threshold, idle_seconds

    def desired_execution_flags(self):
        """Only hold Windows awake while we are actually meant to be active."""
        if self.get_runtime_state() != "active":
            return False, False
        return self.config.prevent_sleep, self.config.keep_display_on

    def sync_execution_state(self):
        """Re-assert the power hold when the desired state changes.

        SetThreadExecutionState is per-thread and lasts until the next call on
        that thread, so this must run on the long-lived activity thread.
        """
        desired = self.desired_execution_flags()
        if desired == self._applied_execution_flags:
            return False
        presence.apply_execution_state(*desired)
        self._applied_execution_flags = desired
        self.logger.info("Execution state: prevent_sleep=%s keep_display_on=%s", *desired)
        return True

    def describe_keep_awake(self):
        parts = []
        if self.config.prevent_sleep:
            parts.append("sleep blocked")
        if self.config.keep_display_on:
            parts.append("screen kept on")
        return ", ".join(parts)

    def get_status_presentation(self):
        now = self.now_provider()
        state = self.get_runtime_state(now)
        override = self.get_active_override(now)
        transition = format_transition(get_next_transition(self.config.schedule, now=now))

        if override:
            until_text = override[1].strftime("%a %H:%M")
            if state == "active":
                return (
                    "Active (until {0})".format(until_text),
                    ModernStyle.SUCCESS,
                    "Temporarily held active until {0}, ignoring the schedule.".format(until_text),
                )
            return (
                "Paused (until {0})".format(until_text),
                ModernStyle.TEXT_DIM,
                "Temporarily paused until {0}.".format(until_text),
            )

        if state == "manual_paused":
            return "Manually Paused", ModernStyle.TEXT_DIM, "Presence activity is paused until you resume it."
        if state == "scheduled_off":
            detail = "Outside the scheduled active windows."
            if transition:
                detail = "{0} {1}".format(detail, transition)
            return "Scheduled Off", ModernStyle.WARNING, detail

        if self.config.idle_aware:
            detail = "Activity every {0}s using {1}, only while you are away for {2}s or more.".format(
                self.config.interval, self.config.activity_type, self.config.idle_threshold
            )
        else:
            detail = "Activity every {0}s using {1}.".format(self.config.interval, self.config.activity_type)

        keep_awake = self.describe_keep_awake()
        if keep_awake:
            detail = "{0} Windows {1}.".format(detail, keep_awake)
        if transition:
            detail = "{0} {1}".format(detail, transition)
        return "Active", ModernStyle.SUCCESS, detail

    def get_tray_title(self):
        status_name, _, _ = self.get_status_presentation()
        transition = format_transition(get_next_transition(self.config.schedule, now=self.now_provider()))
        suffix = " | {0}".format(transition) if transition else ""
        return "{0} - {1}{2}".format(APP_NAME, status_name, suffix)

    def notify(self, message, title=None):
        if not self.config.notifications_enabled or not self.icon:
            return
        try:
            self.icon.notify(message, title or APP_NAME)
        except Exception:
            self.logger.debug("Tray notification not available", exc_info=True)

    def get_icon_image(self, state):
        """Icons are static per state, so build each one once and reuse it."""
        if state not in self._icon_cache:
            self._icon_cache[state] = self.create_icon_image(state)
        return self._icon_cache[state]

    def create_icon_image(self, state):
        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        face = (212, 208, 200, 255)
        light = (255, 255, 255, 255)
        shadow = (128, 128, 128, 255)
        dark = (64, 64, 64, 255)
        title_blue = (0, 0, 128, 255)
        screen_blue = (0, 128, 128, 255)
        state_colors = {
            "active": (0, 128, 0, 255),
            "scheduled_off": (128, 0, 0, 255),
            "manual_paused": (96, 96, 96, 255),
        }

        outer = (8, 8, 56, 56)
        draw.rectangle(outer, fill=face)
        draw.line([(outer[0], outer[3]), (outer[0], outer[1]), (outer[2], outer[1])], fill=light, width=2)
        draw.line([(outer[0] + 1, outer[3] - 1), (outer[0] + 1, outer[1] + 1), (outer[2] - 1, outer[1] + 1)], fill=light)
        draw.line([(outer[0], outer[3]), (outer[2], outer[3]), (outer[2], outer[1])], fill=dark, width=2)
        draw.line([(outer[0] + 1, outer[3] - 1), (outer[2] - 1, outer[3] - 1), (outer[2] - 1, outer[1] + 1)], fill=shadow)

        draw.rectangle((12, 12, 52, 20), fill=title_blue)
        draw.rectangle((14, 24, 50, 42), fill=screen_blue)
        draw.rectangle((13, 23, 51, 43), outline=shadow)

        if state == "active":
            draw.line([(22, 34), (28, 39), (41, 27)], fill=light, width=3)
        elif state == "scheduled_off":
            draw.ellipse((23, 26, 41, 40), outline=light, width=2)
            draw.line([(32, 33), (32, 29)], fill=light, width=2)
            draw.line([(32, 33), (36, 35)], fill=light, width=2)
        else:
            draw.rectangle((25, 27, 29, 39), fill=light)
            draw.rectangle((34, 27, 38, 39), fill=light)

        indicator = state_colors.get(state, state_colors["manual_paused"])
        draw.rectangle((42, 42, 54, 54), fill=indicator)
        draw.line([(42, 54), (42, 42), (54, 42)], fill=light)
        draw.line([(42, 54), (54, 54), (54, 42)], fill=dark)
        return image

    def update_icon(self):
        """Only touch the tray when something the user can see actually changed."""
        if not self.icon:
            return

        state = self.get_runtime_state()
        title = self.get_tray_title()
        if state == self._applied_icon_state and title == self._applied_icon_title:
            return

        if state != self._applied_icon_state:
            self.icon.icon = self.get_icon_image(state)
            self._applied_icon_state = state

        self.icon.title = title
        self._applied_icon_title = title

        try:
            self.icon.update_menu()
        except Exception:
            self.logger.debug("Could not refresh tray menu", exc_info=True)

    def refresh_runtime_state(self, notify=True):
        state = self.get_runtime_state()
        if state == self._last_status:
            self.update_icon()
            return

        self._last_status = state
        status_name, _, detail = self.get_status_presentation()
        self.logger.info("State changed to %s", status_name)
        self.update_icon()
        if notify and self.start_time:
            self.notify(detail, title=status_name)

    def simulate_activity(self):
        try:
            if self.config.activity_type in ("F15 Key (Recommended)", "Both"):
                presence.send_key()

            if self.config.activity_type in ("Mouse Jiggle", "Both"):
                presence.send_mouse_jiggle(zen=self.config.zen_jiggle)

            self.activity_count += 1
            with self.config_lock:
                self.config.lifetime_activity_count += 1
                self.config.last_activity_at = self.now_provider()
                lifetime = self.config.lifetime_activity_count
            self.logger.info("Simulated activity #%s using %s", lifetime, self.config.activity_type)
            return True
        except Exception:
            self.logger.exception("Activity simulation failed")
            return False

    def activity_loop(self):
        next_run = time.monotonic()
        self.refresh_runtime_state(notify=False)

        try:
            while not self.shutdown_event.is_set():
                next_run = self.process_activity_tick(next_run)
                self.shutdown_event.wait(1)
        finally:
            # The hold is bound to this thread, so drop it before we leave.
            presence.release_execution_state()

    def process_activity_tick(self, next_run, now_monotonic=None):
        current_time = time.monotonic() if now_monotonic is None else now_monotonic
        self.clear_expired_override()
        current_state = self.get_runtime_state()
        self.refresh_runtime_state()
        self.sync_execution_state()
        self.flush_config_if_due(current_time)

        if current_state != "active":
            return current_time

        if current_time < next_run:
            return next_run

        if self.get_runtime_state() != "active":
            return current_time

        should_inject, idle_seconds = self.should_inject_now()
        if not should_inject:
            # Check again shortly rather than skipping a whole interval, so we
            # inject promptly once the user steps away.
            self.logger.debug("User active (%.0fs idle); skipping injection", idle_seconds)
            return current_time + min(self.config.interval, 15)

        self.simulate_activity()
        return current_time + self.config.interval

    # The tray is the app for most sessions, so it carries the things people
    # reach for daily rather than just Pause / Settings / Quit.
    OVERRIDE_CHOICES = (("30 minutes", 30), ("1 hour", 60), ("2 hours", 120), ("4 hours", 240))

    def build_tray_menu(self):
        def stay_active(minutes):
            return lambda icon=None, item=None: self.set_override("active", minutes)

        def pause_for(minutes):
            return lambda icon=None, item=None: self.set_override("paused", minutes)

        return pystray.Menu(
            pystray.MenuItem(lambda _: self.get_status_presentation()[0], None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda _: "Resume" if self.manual_paused else "Pause", self.toggle_state, default=True),
            pystray.MenuItem(
                "Stay active for",
                pystray.Menu(*[pystray.MenuItem(label, stay_active(minutes)) for label, minutes in self.OVERRIDE_CHOICES]),
            ),
            pystray.MenuItem(
                "Pause for",
                pystray.Menu(*[pystray.MenuItem(label, pause_for(minutes)) for label, minutes in self.OVERRIDE_CHOICES]),
            ),
            pystray.MenuItem(
                "Clear timer",
                self.clear_override,
                visible=lambda _: self.get_active_override() is not None,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", self.open_settings),
            pystray.MenuItem("Quit", self.quit_app),
        )

    def toggle_state(self, icon=None, item=None):
        # An explicit Pause/Resume overrules whatever timer was running.
        if self.get_active_override():
            with self.config_lock:
                self.config.override_state = None
                self.config.override_until = None

        self.manual_paused = not self.manual_paused
        self.logger.info("Manual pause toggled: %s", self.manual_paused)
        self.refresh_runtime_state()

    def open_settings(self, icon=None, item=None):
        if self.root:
            self.root.after(0, self._show_settings_window)
            return
        self._show_settings_window()

    def _show_settings_window(self):
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self)
        self.settings_window.show()

    def quit_app(self, icon=None, item=None):
        self.shutdown()
        if self.root:
            try:
                self.root.after(0, self.root.quit)
            except Exception:
                pass

    def shutdown(self):
        if self._shutdown_complete:
            return
        self._shutdown_complete = True

        self.logger.info("Shutting down application")
        self.shutdown_event.set()
        if self.thread and self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)

        try:
            self.save_config()
        except Exception:
            self.logger.exception("Could not save config during shutdown")

        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                self.logger.debug("Could not stop tray icon", exc_info=True)

        self.instance.release()

    def run(self):
        if not self.instance.acquire():
            show_message_box("Alive Forever is already running. Check the system tray.")
            return 1

        self.start_time = self.now_provider()

        # Must happen before the first Tk window exists, or Windows will
        # bitmap-stretch the whole UI on a scaled display.
        awareness = enable_dpi_awareness()
        self.display_scaling = get_display_scaling()
        self.logger.info("DPI awareness: %s at %.2fx scaling", awareness or "none", self.display_scaling)
        ModernStyle.apply_scaling(self.display_scaling)

        self.root = tk.Tk()
        self.root.withdraw()
        try:
            self.root.tk.call("tk", "scaling", self.display_scaling * 96.0 / 72.0)
        except tk.TclError:
            self.logger.debug("Could not set Tk scaling", exc_info=True)
        self.logger.info("UI font family: %s", ModernStyle.resolve_fonts(self.root))

        self.repair_startup()

        self.thread = threading.Thread(target=self.activity_loop, daemon=True)
        self.thread.start()

        menu = self.build_tray_menu()

        initial_state = self.get_runtime_state()
        self.icon = pystray.Icon(
            "alive_forever",
            self.get_icon_image(initial_state),
            self.get_tray_title(),
            menu,
        )
        self._applied_icon_state = initial_state
        self._applied_icon_title = self.icon.title

        icon_thread = threading.Thread(target=self.icon.run, daemon=True)
        icon_thread.start()

        self.root.after(300, self.prompt_first_run)
        if not self.config.start_minimized:
            self.root.after(600, self._show_settings_window)

        self.logger.info("Alive Forever started")
        try:
            self.root.mainloop()
        finally:
            self.shutdown()
        return 0


def main():
    if has_console_streams():
        print("=" * 50)
        print("  {0} - Keep Awake & Teams Presence".format(APP_NAME))
        print("=" * 50)
        print("The app runs in your system tray.")
        print("Logs: {0}".format(LOG_DIR / "alive_forever.log"))
        print("-" * 50)

    app = KeepAliveApp()
    return app.run()