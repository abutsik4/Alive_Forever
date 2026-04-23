"""Tk settings window for Alive Forever."""

import tkinter as tk
from tkinter import messagebox

from alive_forever.core.config import PRESET_CONFIGS, VALID_ACTIVITY_TYPES, apply_preset, clamp_interval
from alive_forever.core.scheduler import DAY_LABELS, DAY_ORDER, ScheduleConfig, TimeWindow, describe_schedule, parse_time_string
from alive_forever.system.windows import ICON_FILE


class ModernStyle:
    WINDOW_BG = "#c0c0c0"
    PANEL_BG = "#d4d0c8"
    PANEL_INNER = "#c0c0c0"
    FIELD_BG = "#ffffff"
    TITLE_BG = "#000080"
    TITLE_TEXT = "#ffffff"
    TEXT = "#000000"
    TEXT_DIM = "#3f3f3f"
    BORDER_DARK = "#404040"
    BORDER_SHADOW = "#808080"
    BORDER_LIGHT = "#dfdfdf"
    BORDER_HIGHLIGHT = "#ffffff"
    SELECT_BG = "#000080"
    SELECT_TEXT = "#ffffff"
    SUCCESS = "#008000"
    WARNING = "#800000"
    PAUSED = "#404040"
    FONT_FAMILY = "MS Sans Serif"
    FONT_TITLE = (FONT_FAMILY, 18, "bold")
    FONT_SUBTITLE = (FONT_FAMILY, 10)
    FONT_BODY = (FONT_FAMILY, 10)
    FONT_BODY_BOLD = (FONT_FAMILY, 10, "bold")
    FONT_CAPTION = (FONT_FAMILY, 8, "bold")
    FONT_SMALL = (FONT_FAMILY, 8)


class SettingsWindow:
    WINDOW_WIDTH = 620
    WINDOW_HEIGHT = 860
    MIN_WINDOW_HEIGHT = 520
    WINDOW_MARGIN = 80

    def __init__(self, app):
        self.app = app
        self.window = None
        self.is_open = False
        self._icon_photo = None
        self.window_day_vars = {}
        self.draft_windows = []
        self._content_canvas = None
        self._content_frame = None
        self._content_scrollbar = None

    @classmethod
    def calculate_window_geometry(cls, screen_width, screen_height):
        width = min(cls.WINDOW_WIDTH, max(480, screen_width - cls.WINDOW_MARGIN))
        available_height = max(cls.MIN_WINDOW_HEIGHT, screen_height - cls.WINDOW_MARGIN)
        height = min(cls.WINDOW_HEIGHT, available_height)
        x_pos = max(0, (screen_width - width) // 2)
        y_pos = max(0, (screen_height - height) // 2)
        return width, height, x_pos, y_pos

    def build_schedule_windows_for_save(self):
        windows = [TimeWindow(**window.to_dict()) for window in self.draft_windows]

        if not hasattr(self, "window_start_var") or not hasattr(self, "window_end_var") or not hasattr(self, "windows_listbox"):
            return windows

        selection = self.windows_listbox.curselection()
        if selection:
            windows[selection[0]] = self._window_from_editor()
        return windows

    def show(self):
        if self.window and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            self.window.focus_force()
            return

        self.draft_windows = [TimeWindow(**window.to_dict()) for window in self.app.config.schedule.windows]

        parent = self.app.root if self.app.root else None
        self.window = tk.Toplevel(parent) if parent else tk.Tk()
        self.window.title("Alive Forever - Settings")
        self.window.configure(bg=ModernStyle.WINDOW_BG)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        self.is_open = True

        self.window.update_idletasks()
        width, height, x_pos, y_pos = self.calculate_window_geometry(
            self.window.winfo_screenwidth(),
            self.window.winfo_screenheight(),
        )
        self.window.minsize(480, self.MIN_WINDOW_HEIGHT)
        self.window.resizable(True, True)
        self.window.geometry("{0}x{1}+{2}+{3}".format(width, height, x_pos, y_pos))

        if ICON_FILE.exists():
            try:
                self._icon_photo = tk.PhotoImage(file=str(ICON_FILE))
                self.window.iconphoto(True, self._icon_photo)
            except Exception:
                self.app.logger.debug("Could not set Tk icon", exc_info=True)

        self._create_ui()
        self._populate_windows_list()
        self._refresh_runtime_display()

    def _create_ui(self):
        shell = tk.Frame(self.window, bg=ModernStyle.WINDOW_BG, bd=2, relief=tk.RAISED)
        shell.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        title_bar = tk.Frame(shell, bg=ModernStyle.TITLE_BG, height=28)
        title_bar.pack(fill=tk.X, padx=2, pady=(2, 0))
        title_bar.pack_propagate(False)

        icon_badge = tk.Label(
            title_bar,
            text="A",
            font=ModernStyle.FONT_BODY_BOLD,
            fg=ModernStyle.TITLE_TEXT,
            bg=ModernStyle.TITLE_BG,
            padx=6,
        )
        icon_badge.pack(side=tk.LEFT)
        tk.Label(
            title_bar,
            text="Alive Forever Control Panel",
            font=ModernStyle.FONT_BODY_BOLD,
            fg=ModernStyle.TITLE_TEXT,
            bg=ModernStyle.TITLE_BG,
        ).pack(side=tk.LEFT)

        client_area = tk.Frame(shell, bg=ModernStyle.WINDOW_BG)
        client_area.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self._content_canvas = tk.Canvas(
            client_area,
            bg=ModernStyle.WINDOW_BG,
            highlightthickness=0,
            bd=0,
        )
        self._content_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._content_scrollbar = tk.Scrollbar(
            client_area,
            orient=tk.VERTICAL,
            command=self._content_canvas.yview,
            bg=ModernStyle.PANEL_BG,
            activebackground=ModernStyle.PANEL_INNER,
            troughcolor=ModernStyle.WINDOW_BG,
            relief=tk.RAISED,
            bd=2,
        )
        self._content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._content_canvas.configure(yscrollcommand=self._content_scrollbar.set)

        main_frame = tk.Frame(self._content_canvas, bg=ModernStyle.WINDOW_BG)
        self._content_frame = main_frame
        canvas_window = self._content_canvas.create_window((0, 0), window=main_frame, anchor="nw")
        main_frame.bind("<Configure>", lambda event: self._on_content_configure())
        self._content_canvas.bind("<Configure>", lambda event: self._on_canvas_configure(canvas_window, event.width))
        self._content_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        header = tk.Frame(main_frame, bg=ModernStyle.WINDOW_BG)
        header.pack(fill=tk.X, pady=(2, 14))

        tk.Label(
            header,
            text="Alive Forever",
            font=ModernStyle.FONT_TITLE,
            fg=ModernStyle.TEXT,
            bg=ModernStyle.WINDOW_BG,
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Classic desktop control for tray-based activity keeping",
            font=ModernStyle.FONT_SUBTITLE,
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.WINDOW_BG,
        ).pack(anchor="w")

        status_card = self._create_card(main_frame, "Status")
        status_row = tk.Frame(status_card, bg=ModernStyle.PANEL_BG)
        status_row.pack(fill=tk.X, pady=(0, 8))

        self.status_indicator = tk.Label(status_row, text=chr(254), font=ModernStyle.FONT_BODY_BOLD, bg=ModernStyle.PANEL_BG)
        self.status_indicator.pack(side=tk.LEFT)

        self.status_label = tk.Label(
            status_row,
            text="",
            font=ModernStyle.FONT_BODY_BOLD,
            fg=ModernStyle.TEXT,
            bg=ModernStyle.PANEL_BG,
        )
        self.status_label.pack(side=tk.LEFT, padx=(5, 0))

        self.toggle_btn = self._create_button(status_row, "Pause", self._toggle_status)
        self.toggle_btn.pack(side=tk.RIGHT)

        self.status_detail_label = tk.Label(
            status_card,
            text="",
            font=ModernStyle.FONT_SMALL,
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.PANEL_BG,
            anchor="w",
            justify=tk.LEFT,
            wraplength=520,
        )
        self.status_detail_label.pack(fill=tk.X)

        stats_row = tk.Frame(status_card, bg=ModernStyle.PANEL_BG)
        stats_row.pack(fill=tk.X, pady=(10, 0))

        self.session_label = tk.Label(stats_row, text="Session: 00:00:00", font=ModernStyle.FONT_SMALL, fg=ModernStyle.TEXT_DIM, bg=ModernStyle.PANEL_BG)
        self.session_label.pack(side=tk.LEFT)
        self.activity_label = tk.Label(stats_row, text="Session activities: 0", font=ModernStyle.FONT_SMALL, fg=ModernStyle.TEXT_DIM, bg=ModernStyle.PANEL_BG)
        self.activity_label.pack(side=tk.RIGHT)

        totals_row = tk.Frame(status_card, bg=ModernStyle.PANEL_BG)
        totals_row.pack(fill=tk.X, pady=(6, 0))

        self.total_activity_label = tk.Label(totals_row, text="Lifetime activities: 0", font=ModernStyle.FONT_SMALL, fg=ModernStyle.TEXT_DIM, bg=ModernStyle.PANEL_BG)
        self.total_activity_label.pack(side=tk.LEFT)
        self.last_activity_label = tk.Label(totals_row, text="Last activity: --", font=ModernStyle.FONT_SMALL, fg=ModernStyle.TEXT_DIM, bg=ModernStyle.PANEL_BG)
        self.last_activity_label.pack(side=tk.RIGHT)

        general_card = self._create_card(main_frame, "General")

        self.preset_var = tk.StringVar(value=self.app.config.profile_name)
        self._create_option_row(general_card, "Preset", self.preset_var, list(PRESET_CONFIGS.keys()), self._apply_preset)

        self.interval_var = tk.StringVar(value=str(self.app.config.interval))
        self._create_entry_row(general_card, "Activity Interval", self.interval_var, "seconds")

        self.activity_type_var = tk.StringVar(value=self.app.config.activity_type)
        self._create_option_row(general_card, "Activity Type", self.activity_type_var, VALID_ACTIVITY_TYPES)

        self.startup_var = tk.BooleanVar(value=self.app.is_startup_enabled())
        self._create_toggle_row(general_card, "Start with Windows", self.startup_var)

        self.minimized_var = tk.BooleanVar(value=self.app.config.start_minimized)
        self._create_toggle_row(general_card, "Start Minimized", self.minimized_var)

        self.notifications_var = tk.BooleanVar(value=self.app.config.notifications_enabled)
        self._create_toggle_row(general_card, "Notifications", self.notifications_var)

        schedule_card = self._create_card(main_frame, "Schedule")

        self.schedule_enabled_var = tk.BooleanVar(value=self.app.config.schedule.enabled)
        self._create_toggle_row(schedule_card, "Enable Schedule", self.schedule_enabled_var)

        list_row = tk.Frame(schedule_card, bg=ModernStyle.PANEL_BG)
        list_row.pack(fill=tk.X, pady=(8, 0))

        self.windows_listbox = tk.Listbox(
            list_row,
            height=6,
            bg=ModernStyle.FIELD_BG,
            fg=ModernStyle.TEXT,
            selectbackground=ModernStyle.SELECT_BG,
            selectforeground=ModernStyle.SELECT_TEXT,
            relief=tk.SUNKEN,
            bd=2,
            activestyle="none",
            highlightthickness=0,
        )
        self.windows_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.windows_listbox.bind("<<ListboxSelect>>", self._load_selected_window)

        list_buttons = tk.Frame(list_row, bg=ModernStyle.PANEL_BG)
        list_buttons.pack(side=tk.LEFT, padx=(10, 0), fill=tk.Y)

        self._create_button(list_buttons, "Add Window", self._add_window).pack(fill=tk.X, pady=(0, 6))
        self._create_button(list_buttons, "Update Selected", self._update_window).pack(fill=tk.X, pady=(0, 6))
        self._create_button(list_buttons, "Remove Selected", self._remove_window).pack(fill=tk.X)

        editor_card = tk.Frame(schedule_card, bg=ModernStyle.PANEL_BG, bd=2, relief=tk.GROOVE)
        editor_card.pack(fill=tk.X, pady=(12, 0))

        self.window_start_var = tk.StringVar(value="09:00")
        self._create_entry_row(editor_card, "Window Start", self.window_start_var, "HH:MM")

        self.window_end_var = tk.StringVar(value="17:00")
        self._create_entry_row(editor_card, "Window End", self.window_end_var, "HH:MM")

        default_days = self.app.config.schedule.windows[0].days if self.app.config.schedule.windows else list(DAY_ORDER)
        days_frame = tk.Frame(editor_card, bg=ModernStyle.PANEL_BG)
        days_frame.pack(fill=tk.X, pady=8)
        tk.Label(days_frame, text="Window Days", font=ModernStyle.FONT_BODY, fg=ModernStyle.TEXT, bg=ModernStyle.PANEL_BG).pack(anchor="w")

        chips = tk.Frame(days_frame, bg=ModernStyle.PANEL_INNER, bd=2, relief=tk.SUNKEN)
        chips.pack(fill=tk.X, pady=(8, 0))
        for index, day_code in enumerate(DAY_ORDER):
            day_var = tk.BooleanVar(value=day_code in default_days)
            self.window_day_vars[day_code] = day_var
            check = tk.Checkbutton(
                chips,
                text=DAY_LABELS[day_code],
                variable=day_var,
                bg=ModernStyle.PANEL_INNER,
                fg=ModernStyle.TEXT,
                activebackground=ModernStyle.PANEL_INNER,
                activeforeground=ModernStyle.TEXT,
                selectcolor=ModernStyle.PANEL_BG,
                highlightthickness=1,
                highlightbackground=ModernStyle.PANEL_INNER,
                font=ModernStyle.FONT_SMALL,
                padx=4,
            )
            check.grid(row=index // 4, column=index % 4, sticky="w", padx=(0, 10), pady=(0, 6))

        self.schedule_preview_label = tk.Label(
            schedule_card,
            text="",
            font=ModernStyle.FONT_SMALL,
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.PANEL_BG,
            anchor="w",
            justify=tk.LEFT,
            wraplength=520,
        )
        self.schedule_preview_label.pack(fill=tk.X, pady=(10, 0))

        actions = tk.Frame(main_frame, bg=ModernStyle.WINDOW_BG)
        actions.pack(fill=tk.X, pady=(20, 0))
        self._create_button(actions, "Save Settings", self._save_settings, primary=True).pack(fill=tk.X, ipady=4)

        tk.Label(
            main_frame,
            text="System log: %APPDATA%\\AliveForever\\logs",
            font=ModernStyle.FONT_SMALL,
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.WINDOW_BG,
        ).pack(pady=(15, 0))

    def _on_content_configure(self):
        if self._content_canvas and self._content_frame:
            self._content_canvas.configure(scrollregion=self._content_canvas.bbox("all"))

    def _on_canvas_configure(self, canvas_window, width):
        if self._content_canvas:
            self._content_canvas.itemconfigure(canvas_window, width=width)

    def _on_mousewheel(self, event):
        if not self.window or not self.window.winfo_exists() or not self._content_canvas:
            return

        widget = self.window.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget == self.window:
                delta = -1 * int(event.delta / 120) if event.delta else 0
                if delta:
                    self._content_canvas.yview_scroll(delta, "units")
                return
            widget = widget.master

    def _create_card(self, parent, title):
        card = tk.Frame(parent, bg=ModernStyle.PANEL_BG, bd=2, relief=tk.GROOVE)
        card.pack(fill=tk.X, pady=(0, 12))

        header = tk.Frame(card, bg=ModernStyle.PANEL_BG)
        header.pack(fill=tk.X, padx=10, pady=(8, 4))
        tk.Label(
            header,
            text=title.upper(),
            font=ModernStyle.FONT_CAPTION,
            fg=ModernStyle.TEXT,
            bg=ModernStyle.PANEL_BG,
        ).pack(anchor="w")

        separator = tk.Frame(card, bg=ModernStyle.BORDER_SHADOW, height=2, bd=0)
        separator.pack(fill=tk.X, padx=10)
        tk.Frame(separator, bg=ModernStyle.BORDER_HIGHLIGHT, height=1).pack(fill=tk.X)

        content = tk.Frame(card, bg=ModernStyle.PANEL_BG)
        content.pack(fill=tk.X, padx=12, pady=10)
        return content

    def _create_button(self, parent, text, command, primary=False):
        bg = ModernStyle.PANEL_BG if primary else ModernStyle.PANEL_BG
        fg = ModernStyle.TEXT
        button = tk.Button(
            parent,
            text=text,
            font=ModernStyle.FONT_BODY_BOLD if primary else ModernStyle.FONT_BODY,
            bg=bg,
            fg=fg,
            activebackground=ModernStyle.PANEL_INNER,
            activeforeground=ModernStyle.TEXT,
            relief=tk.RAISED,
            bd=2,
            highlightbackground=ModernStyle.PANEL_BG,
            command=command,
        )
        button.config(padx=12, pady=4)
        return button

    def _create_entry_row(self, parent, label_text, variable, suffix):
        row = tk.Frame(parent, bg=ModernStyle.PANEL_BG)
        row.pack(fill=tk.X, pady=8)
        tk.Label(row, text=label_text, font=ModernStyle.FONT_BODY, fg=ModernStyle.TEXT, bg=ModernStyle.PANEL_BG).pack(side=tk.LEFT)
        right = tk.Frame(row, bg=ModernStyle.PANEL_BG)
        right.pack(side=tk.RIGHT)
        entry = tk.Entry(
            right,
            textvariable=variable,
            width=8,
            font=ModernStyle.FONT_BODY,
            bg=ModernStyle.FIELD_BG,
            fg=ModernStyle.TEXT,
            insertbackground=ModernStyle.TEXT,
            relief=tk.SUNKEN,
            bd=2,
            justify=tk.CENTER,
        )
        entry.pack(side=tk.LEFT, padx=(0, 5), ipady=4)
        tk.Label(right, text=suffix, font=ModernStyle.FONT_BODY, fg=ModernStyle.TEXT_DIM, bg=ModernStyle.PANEL_BG).pack(side=tk.LEFT)

    def _create_option_row(self, parent, label_text, variable, options, command=None):
        row = tk.Frame(parent, bg=ModernStyle.PANEL_BG)
        row.pack(fill=tk.X, pady=8)
        tk.Label(row, text=label_text, font=ModernStyle.FONT_BODY, fg=ModernStyle.TEXT, bg=ModernStyle.PANEL_BG).pack(side=tk.LEFT)
        container = tk.Frame(row, bg=ModernStyle.PANEL_BG, bd=2, relief=tk.RAISED)
        container.pack(side=tk.RIGHT)
        menu = tk.OptionMenu(container, variable, *options, command=command)
        menu.config(
            font=ModernStyle.FONT_BODY,
            bg=ModernStyle.PANEL_BG,
            fg=ModernStyle.TEXT,
            activebackground=ModernStyle.PANEL_INNER,
            activeforeground=ModernStyle.TEXT,
            highlightthickness=0,
            bd=0,
            relief=tk.FLAT,
            padx=6,
        )
        menu["menu"].config(
            bg=ModernStyle.FIELD_BG,
            fg=ModernStyle.TEXT,
            activebackground=ModernStyle.SELECT_BG,
            activeforeground=ModernStyle.SELECT_TEXT,
            font=ModernStyle.FONT_BODY,
        )
        menu.pack()

    def _create_toggle_row(self, parent, label_text, variable):
        row = tk.Frame(parent, bg=ModernStyle.PANEL_BG)
        row.pack(fill=tk.X, pady=8)
        tk.Label(row, text=label_text, font=ModernStyle.FONT_BODY, fg=ModernStyle.TEXT, bg=ModernStyle.PANEL_BG).pack(side=tk.LEFT)
        toggle = tk.Checkbutton(
            row,
            variable=variable,
            text="",
            bg=ModernStyle.PANEL_BG,
            fg=ModernStyle.TEXT,
            activebackground=ModernStyle.PANEL_BG,
            activeforeground=ModernStyle.TEXT,
            selectcolor=ModernStyle.PANEL_BG,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=ModernStyle.PANEL_BG,
            font=ModernStyle.FONT_BODY,
        )
        toggle.pack(side=tk.RIGHT)

    def _populate_windows_list(self):
        self.windows_listbox.delete(0, tk.END)
        for window in self.draft_windows:
            self.windows_listbox.insert(tk.END, window.label())
        self._update_schedule_preview()

    def _window_from_editor(self):
        start = self.window_start_var.get().strip()
        end = self.window_end_var.get().strip()
        parse_time_string(start)
        parse_time_string(end)
        days = [day for day in DAY_ORDER if self.window_day_vars[day].get()]
        if not days:
            raise ValueError("Select at least one day for the window.")
        return TimeWindow(start=start, end=end, days=days)

    def _load_selected_window(self, event=None):
        selection = self.windows_listbox.curselection()
        if not selection:
            return
        window = self.draft_windows[selection[0]]
        self.window_start_var.set(window.start)
        self.window_end_var.set(window.end)
        for day_code in DAY_ORDER:
            self.window_day_vars[day_code].set(day_code in window.days)

    def _add_window(self):
        try:
            self.draft_windows.append(self._window_from_editor())
            self._populate_windows_list()
        except ValueError as error:
            messagebox.showerror("Error", str(error))

    def _update_window(self):
        selection = self.windows_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Select a schedule window to update.")
            return
        try:
            self.draft_windows[selection[0]] = self._window_from_editor()
            self._populate_windows_list()
            self.windows_listbox.selection_set(selection[0])
        except ValueError as error:
            messagebox.showerror("Error", str(error))

    def _remove_window(self):
        selection = self.windows_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Select a schedule window to remove.")
            return
        del self.draft_windows[selection[0]]
        self._populate_windows_list()

    def _apply_preset(self, preset_name):
        preview_config = self.app.config.clone()
        apply_preset(preview_config, preset_name)
        self.interval_var.set(str(preview_config.interval))
        self.activity_type_var.set(preview_config.activity_type)
        self.schedule_enabled_var.set(preview_config.schedule.enabled)
        self.draft_windows = [TimeWindow(**window.to_dict()) for window in preview_config.schedule.windows]
        self._populate_windows_list()
        if self.draft_windows:
            first_window = self.draft_windows[0]
            self.window_start_var.set(first_window.start)
            self.window_end_var.set(first_window.end)
            for day_code in DAY_ORDER:
                self.window_day_vars[day_code].set(day_code in first_window.days)

    def _update_schedule_preview(self):
        preview_schedule = ScheduleConfig(enabled=self.schedule_enabled_var.get(), windows=list(self.draft_windows))
        self.schedule_preview_label.config(text=describe_schedule(preview_schedule))

    def _toggle_status(self):
        self.app.toggle_state()
        self._refresh_runtime_display()

    def _refresh_runtime_display(self):
        if not self.window or not self.window.winfo_exists():
            self.is_open = False
            return

        try:
            status_name, color, detail = self.app.get_status_presentation()
            self.status_indicator.config(fg=color)
            self.status_label.config(text=status_name)
            self.status_detail_label.config(text=detail)
            self.toggle_btn.config(text="Resume" if self.app.manual_paused else "Pause")

            if self.app.start_time:
                elapsed = self.app.now_provider() - self.app.start_time
                hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                self.session_label.config(text="Session: {0:02d}:{1:02d}:{2:02d}".format(hours, minutes, seconds))

            self.activity_label.config(text="Session activities: {0}".format(self.app.activity_count))
            self.total_activity_label.config(text="Lifetime activities: {0}".format(self.app.config.lifetime_activity_count))
            if self.app.config.last_activity_at:
                self.last_activity_label.config(
                    text="Last activity: {0}".format(self.app.config.last_activity_at.strftime("%a %H:%M:%S"))
                )
            else:
                self.last_activity_label.config(text="Last activity: --")

            self._update_schedule_preview()
            self.window.after(1000, self._refresh_runtime_display)
        except tk.TclError:
            self.is_open = False

    def _save_settings(self):
        try:
            raw_interval = self.interval_var.get().strip()
            interval = clamp_interval(raw_interval)
            if str(interval) != raw_interval:
                raise ValueError("Interval must be between 10 and 300 seconds.")

            activity_type = self.activity_type_var.get()
            if activity_type not in VALID_ACTIVITY_TYPES:
                raise ValueError("Select a valid activity type.")

            schedule_windows = self.build_schedule_windows_for_save()
            if self.schedule_enabled_var.get() and not schedule_windows:
                raise ValueError("Add at least one schedule window or disable scheduling.")

            updated_config = self.app.config.clone()
            updated_config.interval = interval
            updated_config.activity_type = activity_type
            updated_config.start_minimized = self.minimized_var.get()
            updated_config.notifications_enabled = self.notifications_var.get()
            updated_config.profile_name = self.preset_var.get() if self.preset_var.get() in PRESET_CONFIGS else "Custom"
            updated_config.schedule = ScheduleConfig(
                enabled=self.schedule_enabled_var.get(),
                windows=schedule_windows,
            )

            self.app.set_startup_enabled(self.startup_var.get())
            self.app.apply_config(updated_config)
            messagebox.showinfo("Saved", "Settings saved successfully.")
        except ValueError as error:
            messagebox.showerror("Error", str(error))
        except Exception as error:
            self.app.logger.exception("Could not save settings")
            messagebox.showerror("Error", "Could not save settings:\n{0}".format(error))

    def _on_close(self):
        self.is_open = False
        if self._content_canvas:
            self._content_canvas.unbind_all("<MouseWheel>")
        if self.window:
            self.window.destroy()
            self.window = None