"""
Alive Forever - MS Teams Status Keeper
Keeps your Microsoft Teams status as "Active" by simulating subtle activity.
Features a modern settings interface and system tray integration.
"""

import sys
import os
import ctypes
import time
import json
import threading
import winreg
from datetime import datetime, timedelta
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    print("Installing required packages...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pystray", "pillow"])
    import pystray
    from PIL import Image, ImageDraw

import tkinter as tk
from tkinter import messagebox


# Get the directory where the script is located
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
APP_NAME = "Alive Forever"
STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class ModernStyle:
    """Modern dark theme styling."""
    BG_DARK = "#1a1a2e"
    BG_CARD = "#16213e"
    BG_INPUT = "#0f3460"
    ACCENT = "#00d9ff"
    ACCENT_HOVER = "#00b8d4"
    SUCCESS = "#00e676"
    TEXT = "#ffffff"
    TEXT_DIM = "#8892b0"
    BORDER = "#233554"


class SettingsWindow:
    """Modern settings interface."""
    
    def __init__(self, keep_alive):
        self.keep_alive = keep_alive
        self.window = None
        self.is_open = False
        
    def show(self):
        """Create and show the settings window."""
        if self.is_open:
            return
            
        self.is_open = True
        self.window = tk.Toplevel() if hasattr(tk, '_default_root') and tk._default_root else tk.Tk()
        self.window.title(f"{APP_NAME} - Settings")
        self.window.geometry("420x520")
        self.window.resizable(False, False)
        self.window.configure(bg=ModernStyle.BG_DARK)
        
        # Center window on screen
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - 420) // 2
        y = (self.window.winfo_screenheight() - 520) // 2
        self.window.geometry(f"+{x}+{y}")
        
        # Set window icon
        try:
            icon_path = SCRIPT_DIR / "icon.png"
            if icon_path.exists():
                icon_image = Image.open(icon_path)
                icon_photo = tk.PhotoImage(file=str(icon_path))
                self.window.iconphoto(True, icon_photo)
                self._icon_photo = icon_photo  # Keep reference to prevent garbage collection
        except Exception:
            pass  # Fallback to default icon
        
        self._create_ui()
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Don't call mainloop - let the main app handle it
        if not hasattr(tk, '_default_root') or not tk._default_root:
            self.window.mainloop()
        
    def _create_ui(self):
        """Create the settings UI elements."""
        main_frame = tk.Frame(self.window, bg=ModernStyle.BG_DARK)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Header
        header_frame = tk.Frame(main_frame, bg=ModernStyle.BG_DARK)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        title = tk.Label(
            header_frame,
            text="⚡ Alive Forever",
            font=("Segoe UI", 22, "bold"),
            fg=ModernStyle.ACCENT,
            bg=ModernStyle.BG_DARK
        )
        title.pack(anchor="w")
        
        subtitle = tk.Label(
            header_frame,
            text="Keep Teams Active",
            font=("Segoe UI", 11),
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.BG_DARK
        )
        subtitle.pack(anchor="w")
        
        # Status Card
        status_card = self._create_card(main_frame, "Status")
        
        status_frame = tk.Frame(status_card, bg=ModernStyle.BG_CARD)
        status_frame.pack(fill=tk.X, pady=5)
        
        self.status_indicator = tk.Label(
            status_frame,
            text="●",
            font=("Segoe UI", 16),
            fg=ModernStyle.SUCCESS if self.keep_alive.running else ModernStyle.TEXT_DIM,
            bg=ModernStyle.BG_CARD
        )
        self.status_indicator.pack(side=tk.LEFT)
        
        self.status_label = tk.Label(
            status_frame,
            text="Active" if self.keep_alive.running else "Paused",
            font=("Segoe UI", 12),
            fg=ModernStyle.TEXT,
            bg=ModernStyle.BG_CARD
        )
        self.status_label.pack(side=tk.LEFT, padx=(5, 0))
        
        self.toggle_btn = self._create_button(
            status_frame,
            "Pause" if self.keep_alive.running else "Start",
            self._toggle_status
        )
        self.toggle_btn.pack(side=tk.RIGHT)
        
        # Stats row
        stats_frame = tk.Frame(status_card, bg=ModernStyle.BG_CARD)
        stats_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.uptime_label = tk.Label(
            stats_frame,
            text="Session: --:--:--",
            font=("Segoe UI", 9),
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.BG_CARD
        )
        self.uptime_label.pack(side=tk.LEFT)
        
        self.activity_label = tk.Label(
            stats_frame,
            text=f"Activities: {self.keep_alive.activity_count}",
            font=("Segoe UI", 9),
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.BG_CARD
        )
        self.activity_label.pack(side=tk.RIGHT)
        
        # Settings Card
        settings_card = self._create_card(main_frame, "Settings")
        
        # Interval setting
        interval_frame = tk.Frame(settings_card, bg=ModernStyle.BG_CARD)
        interval_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(
            interval_frame,
            text="Activity Interval",
            font=("Segoe UI", 11),
            fg=ModernStyle.TEXT,
            bg=ModernStyle.BG_CARD
        ).pack(side=tk.LEFT)
        
        interval_right = tk.Frame(interval_frame, bg=ModernStyle.BG_CARD)
        interval_right.pack(side=tk.RIGHT)
        
        self.interval_var = tk.StringVar(value=str(self.keep_alive.interval))
        self.interval_entry = tk.Entry(
            interval_right,
            textvariable=self.interval_var,
            width=6,
            font=("Segoe UI", 10),
            bg=ModernStyle.BG_INPUT,
            fg=ModernStyle.TEXT,
            insertbackground=ModernStyle.TEXT,
            relief=tk.FLAT,
            justify=tk.CENTER
        )
        self.interval_entry.pack(side=tk.LEFT, padx=5, ipady=4)
        
        tk.Label(
            interval_right,
            text="seconds",
            font=("Segoe UI", 10),
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.BG_CARD
        ).pack(side=tk.LEFT)
        
        # Activity type setting
        type_frame = tk.Frame(settings_card, bg=ModernStyle.BG_CARD)
        type_frame.pack(fill=tk.X, pady=8)
        
        tk.Label(
            type_frame,
            text="Activity Type",
            font=("Segoe UI", 11),
            fg=ModernStyle.TEXT,
            bg=ModernStyle.BG_CARD
        ).pack(side=tk.LEFT)
        
        # Create a frame to contain the dropdown
        dropdown_container = tk.Frame(type_frame, bg=ModernStyle.BG_INPUT)
        dropdown_container.pack(side=tk.RIGHT)
        
        self.activity_type_var = tk.StringVar(value=self.keep_alive.activity_type)
        activity_options = ["F15 Key (Recommended)", "Mouse Jiggle", "Both"]
        type_menu = tk.OptionMenu(dropdown_container, self.activity_type_var, *activity_options)
        type_menu.config(
            font=("Segoe UI", 10),
            bg=ModernStyle.BG_INPUT,
            fg=ModernStyle.TEXT,
            activebackground=ModernStyle.ACCENT,
            activeforeground=ModernStyle.TEXT,
            highlightthickness=0,
            bd=0,
            relief=tk.FLAT,
            padx=8
        )
        type_menu["menu"].config(
            bg=ModernStyle.BG_INPUT,
            fg=ModernStyle.TEXT,
            activebackground=ModernStyle.ACCENT,
            activeforeground=ModernStyle.TEXT,
            font=("Segoe UI", 10)
        )
        type_menu.pack()
        
        # Startup option
        startup_frame = tk.Frame(settings_card, bg=ModernStyle.BG_CARD)
        startup_frame.pack(fill=tk.X, pady=8)
        
        tk.Label(
            startup_frame,
            text="Start with Windows",
            font=("Segoe UI", 11),
            fg=ModernStyle.TEXT,
            bg=ModernStyle.BG_CARD
        ).pack(side=tk.LEFT)
        
        self.startup_var = tk.BooleanVar(value=self._is_startup_enabled())
        startup_check = tk.Checkbutton(
            startup_frame,
            variable=self.startup_var,
            text="",
            bg=ModernStyle.BG_CARD,
            fg=ModernStyle.TEXT,
            activebackground=ModernStyle.BG_CARD,
            activeforeground=ModernStyle.TEXT,
            selectcolor=ModernStyle.BG_INPUT,
            highlightthickness=0,
            command=self._toggle_startup
        )
        startup_check.pack(side=tk.RIGHT)
        
        # Minimize to tray
        tray_frame = tk.Frame(settings_card, bg=ModernStyle.BG_CARD)
        tray_frame.pack(fill=tk.X, pady=8)
        
        tk.Label(
            tray_frame,
            text="Start Minimized",
            font=("Segoe UI", 11),
            fg=ModernStyle.TEXT,
            bg=ModernStyle.BG_CARD
        ).pack(side=tk.LEFT)
        
        self.minimized_var = tk.BooleanVar(value=self.keep_alive.start_minimized)
        minimized_check = tk.Checkbutton(
            tray_frame,
            variable=self.minimized_var,
            text="",
            bg=ModernStyle.BG_CARD,
            fg=ModernStyle.TEXT,
            activebackground=ModernStyle.BG_CARD,
            activeforeground=ModernStyle.TEXT,
            selectcolor=ModernStyle.BG_INPUT,
            highlightthickness=0
        )
        minimized_check.pack(side=tk.RIGHT)
        
        # Save Button
        save_frame = tk.Frame(main_frame, bg=ModernStyle.BG_DARK)
        save_frame.pack(fill=tk.X, pady=(20, 0))
        
        save_btn = self._create_button(save_frame, "💾 Save Settings", self._save_settings, primary=True)
        save_btn.pack(fill=tk.X, ipady=8)
        
        # Footer
        footer = tk.Label(
            main_frame,
            text="Tip: The app runs in your system tray when closed",
            font=("Segoe UI", 9),
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.BG_DARK
        )
        footer.pack(pady=(15, 0))
        
        # Start update loop
        self._update_stats()
        
    def _create_card(self, parent, title):
        """Create a styled card container."""
        card = tk.Frame(parent, bg=ModernStyle.BG_CARD)
        card.pack(fill=tk.X, pady=(0, 15))
        
        # Card header
        header_line = tk.Frame(card, bg=ModernStyle.BG_CARD)
        header_line.pack(fill=tk.X, padx=15, pady=(12, 8))
        
        tk.Label(
            header_line,
            text=title.upper(),
            font=("Segoe UI", 9, "bold"),
            fg=ModernStyle.ACCENT,
            bg=ModernStyle.BG_CARD
        ).pack(anchor="w")
        
        # Separator
        sep = tk.Frame(card, bg=ModernStyle.BORDER, height=1)
        sep.pack(fill=tk.X, padx=15)
        
        # Content frame
        content = tk.Frame(card, bg=ModernStyle.BG_CARD)
        content.pack(fill=tk.X, padx=15, pady=10)
        
        return content
        
    def _create_button(self, parent, text, command, primary=False):
        """Create a styled button."""
        bg = ModernStyle.ACCENT if primary else ModernStyle.BG_INPUT
        
        btn = tk.Button(
            parent,
            text=text,
            font=("Segoe UI", 10, "bold" if primary else "normal"),
            bg=bg,
            fg=ModernStyle.TEXT if primary else ModernStyle.TEXT_DIM,
            activebackground=ModernStyle.ACCENT_HOVER if primary else ModernStyle.BG_CARD,
            activeforeground=ModernStyle.TEXT,
            relief=tk.FLAT,
            cursor="hand2",
            command=command
        )
        btn.config(padx=15, pady=3)
        return btn
        
    def _toggle_status(self):
        """Toggle the keep-alive status."""
        self.keep_alive.toggle_state()
        self._update_status_display()
        
    def _update_status_display(self):
        """Update the status display elements."""
        if self.keep_alive.running:
            self.status_indicator.config(fg=ModernStyle.SUCCESS)
            self.status_label.config(text="Active")
            self.toggle_btn.config(text="Pause")
        else:
            self.status_indicator.config(fg=ModernStyle.TEXT_DIM)
            self.status_label.config(text="Paused")
            self.toggle_btn.config(text="Start")
            
    def _update_stats(self):
        """Update statistics display."""
        if self.window and self.is_open:
            try:
                # Update uptime
                if self.keep_alive.start_time:
                    elapsed = datetime.now() - self.keep_alive.start_time
                    hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    self.uptime_label.config(text=f"Session: {hours:02d}:{minutes:02d}:{seconds:02d}")
                
                # Update activity count
                self.activity_label.config(text=f"Activities: {self.keep_alive.activity_count}")
                
                # Schedule next update
                self.window.after(1000, self._update_stats)
            except tk.TclError:
                # Window was closed
                self.is_open = False
            
    def _is_startup_enabled(self):
        """Check if app is set to run at startup."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return True
        except:
            return False
            
    def _toggle_startup(self):
        """Enable or disable startup with Windows."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_SET_VALUE)
            if self.startup_var.get():
                # Get the path to run.bat
                run_bat = SCRIPT_DIR / "run.bat"
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, str(run_bat))
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            messagebox.showerror("Error", f"Could not modify startup settings:\n{e}")
            
    def _save_settings(self):
        """Save all settings."""
        try:
            interval = int(self.interval_var.get())
            if interval < 10:
                messagebox.showwarning("Warning", "Interval should be at least 10 seconds")
                return
            if interval > 300:
                messagebox.showwarning("Warning", "Interval should not exceed 300 seconds (5 minutes)")
                return
                
            self.keep_alive.interval = interval
            self.keep_alive.activity_type = self.activity_type_var.get()
            self.keep_alive.start_minimized = self.minimized_var.get()
            self.keep_alive.save_config()
            
            messagebox.showinfo("Saved", "Settings saved successfully!")
            
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid number for interval")
            
    def _on_close(self):
        """Handle window close."""
        self.is_open = False
        if self.window:
            self.window.destroy()
            self.window = None


class KeepAlive:
    """Main keep-alive application."""
    
    def __init__(self):
        self.running = False
        self.interval = 60  # seconds between activity simulations
        self.activity_type = "F15 Key (Recommended)"
        self.start_minimized = True
        self.thread = None
        self.icon = None
        self.activity_count = 0
        self.start_time = None
        self.settings_window = None
        self.root = None  # Tkinter root window
        
        # Load saved config
        self.load_config()
        
    def load_config(self):
        """Load configuration from file."""
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self.interval = config.get('interval', 60)
                    self.activity_type = config.get('activity_type', "F15 Key (Recommended)")
                    self.start_minimized = config.get('start_minimized', True)
        except Exception as e:
            print(f"Could not load config: {e}")
            
    def save_config(self):
        """Save configuration to file."""
        try:
            config = {
                'interval': self.interval,
                'activity_type': self.activity_type,
                'start_minimized': self.start_minimized
            }
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Could not save config: {e}")
        
    def simulate_activity(self):
        """Simulate activity based on selected type."""
        activity_type = self.activity_type
        
        if "F15" in activity_type or "Both" in activity_type:
            # F15 key - invisible to user but detected by Windows
            VK_F15 = 0x7E
            KEYEVENTF_KEYUP = 0x0002
            ctypes.windll.user32.keybd_event(VK_F15, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_F15, 0, KEYEVENTF_KEYUP, 0)
            
        if "Mouse" in activity_type or "Both" in activity_type:
            # Tiny mouse movement - move 1 pixel and back
            MOUSEEVENTF_MOVE = 0x0001
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, 1, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, -1, 0, 0, 0)
        
        self.activity_count += 1
        
    def activity_loop(self):
        """Main loop that keeps running to simulate activity."""
        while self.running:
            self.simulate_activity()
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] Activity #{self.activity_count} simulated")
            
            # Sleep in small increments to allow quick stopping
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)
    
    def start(self):
        """Start the keep-alive process."""
        if not self.running:
            self.running = True
            self.start_time = datetime.now()
            self.thread = threading.Thread(target=self.activity_loop, daemon=True)
            self.thread.start()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Keep-alive STARTED")
            
    def stop(self):
        """Stop the keep-alive process."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Keep-alive STOPPED")
    
    def create_icon_image(self, active=True):
        """Create a simple icon for the system tray."""
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Draw a circle - cyan/green if active, gray if stopped
        color = (0, 217, 255) if active else (128, 128, 128)
        padding = 4
        draw.ellipse([padding, padding, size - padding, size - padding], fill=color)
        
        # Draw a check mark or pause symbol
        if active:
            # Check mark
            draw.line([(18, 32), (28, 44), (46, 20)], fill='white', width=4)
        else:
            # Pause bars
            draw.rectangle([22, 18, 30, 46], fill='white')
            draw.rectangle([34, 18, 42, 46], fill='white')
            
        return image
    
    def update_icon(self):
        """Update the tray icon based on current state."""
        if self.icon:
            self.icon.icon = self.create_icon_image(self.running)
            status = "Active" if self.running else "Paused"
            self.icon.title = f"{APP_NAME} - {status}"
    
    def toggle_state(self, icon=None, item=None):
        """Toggle between running and stopped states."""
        if self.running:
            self.stop()
        else:
            self.start()
        self.update_icon()
        
    def open_settings(self, icon=None, item=None):
        """Open the settings window - runs on main thread via root.after."""
        if self.root:
            self.root.after(0, self._show_settings_window)
        else:
            # Fallback: create root and show
            self._show_settings_window()
        
    def _show_settings_window(self):
        """Show the settings window."""
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self)
        self.settings_window.show()
        
    def quit_app(self, icon=None, item=None):
        """Quit the application."""
        self.stop()
        self.save_config()
        if self.root:
            self.root.quit()
        if self.icon:
            self.icon.stop()
    
    def run(self):
        """Run the application with system tray icon."""
        # Create hidden tkinter root for thread-safe GUI operations
        self.root = tk.Tk()
        self.root.withdraw()  # Hide the root window
        
        # Create menu
        menu = pystray.Menu(
            pystray.MenuItem(
                lambda text: "⏸ Pause" if self.running else "▶ Resume",
                self.toggle_state,
                default=True
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("⚙ Settings", self.open_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("✕ Quit", self.quit_app)
        )
        
        # Create the tray icon
        self.icon = pystray.Icon(
            "alive_forever",
            self.create_icon_image(True),
            f"{APP_NAME} - Starting...",
            menu
        )
        
        # Start keep-alive automatically
        self.start()
        self.update_icon()
        
        # Run pystray in a separate thread
        icon_thread = threading.Thread(target=self.icon.run, daemon=True)
        icon_thread.start()
        
        # If not starting minimized, show settings after a delay
        if not self.start_minimized:
            self.root.after(500, self._show_settings_window)
        
        # Run tkinter mainloop on main thread (required for thread safety)
        self.root.mainloop()


def main():
    print("=" * 50)
    print(f"  {APP_NAME} - MS Teams Status Keeper")
    print("=" * 50)
    print("\nThe app is running in your system tray.")
    print("Right-click the icon for options.")
    print("-" * 50)
    
    app = KeepAlive()
    app.run()


if __name__ == "__main__":
    main()
