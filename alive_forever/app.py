"""Application entrypoint and tray runtime."""

import ctypes
import sys
import threading
import time
from datetime import datetime

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "pystray", "pillow"])
    import pystray
    from PIL import Image, ImageDraw

import tkinter as tk

from alive_forever.core.config import load_app_config, save_app_config
from alive_forever.core.scheduler import format_transition, get_next_transition, is_schedule_active
from alive_forever.system.windows import (
    APP_NAME,
    LOG_DIR,
    MUTEX_NAME,
    ROOT_DIR,
    SingleInstance,
    build_startup_command,
    is_startup_enabled,
    set_startup_enabled,
    setup_logging,
    show_message_box,
)
from alive_forever.ui.settings import ModernStyle, SettingsWindow


LOGGER = setup_logging()


class KeepAliveApp:
    def __init__(self):
        self.logger = LOGGER
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

    def now_provider(self):
        return datetime.now()

    def apply_config(self, config):
        self.config = config
        save_app_config(self.config, self.logger)
        self.refresh_runtime_state(notify=False)

    def save_config(self):
        save_app_config(self.config, self.logger)

    def is_startup_enabled(self):
        return is_startup_enabled()

    def set_startup_enabled(self, enabled):
        script_path = ROOT_DIR / "keep_alive.py"
        set_startup_enabled(enabled, build_startup_command(script_path), self.logger)

    def get_runtime_state(self, now=None):
        if self.manual_paused:
            return "manual_paused"
        return "active" if is_schedule_active(self.config.schedule, now=now or self.now_provider()) else "scheduled_off"

    def get_status_presentation(self):
        state = self.get_runtime_state()
        transition = format_transition(get_next_transition(self.config.schedule, now=self.now_provider()))

        if state == "manual_paused":
            return "Manually Paused", ModernStyle.TEXT_DIM, "Presence activity is paused until you resume it."
        if state == "scheduled_off":
            detail = "Outside the scheduled active windows."
            if transition:
                detail = "{0} {1}".format(detail, transition)
            return "Scheduled Off", ModernStyle.WARNING, detail

        detail = "Simulating activity every {0} seconds using {1}.".format(self.config.interval, self.config.activity_type)
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
        if not self.icon:
            return
        state = self.get_runtime_state()
        self.icon.icon = self.create_icon_image(state)
        self.icon.title = self.get_tray_title()
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
                virtual_key = 0x7E
                key_up = 0x0002
                ctypes.windll.user32.keybd_event(virtual_key, 0, 0, 0)
                ctypes.windll.user32.keybd_event(virtual_key, 0, key_up, 0)

            if self.config.activity_type in ("Mouse Jiggle", "Both"):
                mouse_move = 0x0001
                ctypes.windll.user32.mouse_event(mouse_move, 1, 0, 0, 0)
                time.sleep(0.05)
                ctypes.windll.user32.mouse_event(mouse_move, -1, 0, 0, 0)

            self.activity_count += 1
            self.config.lifetime_activity_count += 1
            self.config.last_activity_at = self.now_provider()
            self.logger.info("Simulated activity #%s using %s", self.config.lifetime_activity_count, self.config.activity_type)
            return True
        except Exception:
            self.logger.exception("Activity simulation failed")
            return False

    def activity_loop(self):
        next_run = time.monotonic()
        self.refresh_runtime_state(notify=False)

        while not self.shutdown_event.is_set():
            next_run = self.process_activity_tick(next_run)
            self.shutdown_event.wait(1)

    def process_activity_tick(self, next_run, now_monotonic=None):
        current_time = time.monotonic() if now_monotonic is None else now_monotonic
        current_state = self.get_runtime_state()
        self.refresh_runtime_state()

        if current_state != "active":
            return current_time

        if current_time < next_run:
            return next_run

        if self.get_runtime_state() != "active":
            return current_time

        self.simulate_activity()
        return current_time + self.config.interval

    def toggle_state(self, icon=None, item=None):
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
        self.root = tk.Tk()
        self.root.withdraw()

        self.thread = threading.Thread(target=self.activity_loop, daemon=True)
        self.thread.start()

        menu = pystray.Menu(
            pystray.MenuItem(lambda _: "Resume" if self.manual_paused else "Pause", self.toggle_state, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", self.open_settings),
            pystray.MenuItem("Quit", self.quit_app),
        )

        self.icon = pystray.Icon(
            "alive_forever",
            self.create_icon_image(self.get_runtime_state()),
            self.get_tray_title(),
            menu,
        )

        icon_thread = threading.Thread(target=self.icon.run, daemon=True)
        icon_thread.start()

        if not self.config.start_minimized:
            self.root.after(400, self._show_settings_window)

        self.logger.info("Alive Forever started")
        try:
            self.root.mainloop()
        finally:
            self.shutdown()
        return 0


def main():
    print("=" * 50)
    print("  {0} - MS Teams Status Keeper".format(APP_NAME))
    print("=" * 50)
    print("The app runs in your system tray.")
    print("Logs: {0}".format(LOG_DIR / "alive_forever.log"))
    print("-" * 50)

    app = KeepAliveApp()
    return app.run()