"""Tk settings window for Alive Forever.

The window is organised as Windows 95 style tabs rather than one long scrolling
column: six general options never justified a scrollbar, and the canvas plus
global mousewheel binding it required were a large amount of plumbing for a
worse result. The schedule is edited as a 7x24 grid, which also removes the
"typed a window but forgot to press Add" failure the old editor allowed.
"""

import tkinter as tk
from tkinter import messagebox

from alive_forever.core.config import (
    PRESET_CONFIGS,
    VALID_ACTIVITY_TYPES,
    apply_preset,
    clamp_idle_threshold,
    clamp_interval,
)
from alive_forever.core.scheduler import (
    DAY_LABELS,
    DAY_ORDER,
    ScheduleConfig,
    TimeWindow,
    describe_schedule,
    grid_to_windows,
    schedule_uses_minute_precision,
    windows_to_grid,
)
from alive_forever.system.windows import APP_NAME, ICON_FILE, LOG_DIR


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

    # MS Sans Serif has not shipped since Windows 98; on 10/11 Tk silently
    # substitutes something else, so the retro look varied by machine. Ask for
    # the closest face that is actually installed instead.
    FONT_PREFERENCES = ("MS Sans Serif", "Microsoft Sans Serif", "Tahoma", "Segoe UI", "Arial")
    FONT_FAMILY = "Tahoma"
    SCALE = 1.0

    FONT_TITLE = (FONT_FAMILY, 18, "bold")
    FONT_SUBTITLE = (FONT_FAMILY, 10)
    FONT_BODY = (FONT_FAMILY, 10)
    FONT_BODY_BOLD = (FONT_FAMILY, 10, "bold")
    FONT_CAPTION = (FONT_FAMILY, 8, "bold")
    FONT_SMALL = (FONT_FAMILY, 8)

    @classmethod
    def apply_scaling(cls, scale):
        """Record the display scale used for pixel-sized layout constants.

        Font point sizes are deliberately left alone: Tk already scales those
        through `tk scaling`, so multiplying here too would double-apply it.
        """
        cls.SCALE = max(1.0, min(3.0, float(scale)))

    @classmethod
    def resolve_fonts(cls, root):
        """Pick the first preferred family that is actually installed."""
        try:
            from tkinter import font as tk_font

            available = {name.lower() for name in tk_font.families(root)}
        except Exception:
            return cls.FONT_FAMILY

        for candidate in cls.FONT_PREFERENCES:
            if candidate.lower() in available:
                cls.FONT_FAMILY = candidate
                break

        family = cls.FONT_FAMILY
        cls.FONT_TITLE = (family, 18, "bold")
        cls.FONT_SUBTITLE = (family, 10)
        cls.FONT_BODY = (family, 10)
        cls.FONT_BODY_BOLD = (family, 10, "bold")
        cls.FONT_CAPTION = (family, 8, "bold")
        cls.FONT_SMALL = (family, 8)
        return family


class ScheduleGrid:
    """A 7x24 click-and-drag grid of active hours.

    Drawn on a canvas rather than as 168 widgets: painting a drag across a
    hundred cells has to stay cheap, and a canvas gives pixel control over the
    Win95 cell bevels.
    """

    LABEL_WIDTH = 32
    HEADER_HEIGHT = 16
    CELL_WIDTH = 20
    CELL_HEIGHT = 17

    def __init__(self, parent, cells, on_change):
        self.on_change = on_change
        self.cells = set(cells)
        self._paint_value = True

        scale = ModernStyle.SCALE
        self.label_width = round(self.LABEL_WIDTH * scale)
        self.header_height = round(self.HEADER_HEIGHT * scale)
        self.cell_width = round(self.CELL_WIDTH * scale)
        self.cell_height = round(self.CELL_HEIGHT * scale)

        width = self.label_width + self.cell_width * 24
        height = self.header_height + self.cell_height * 7

        self.canvas = tk.Canvas(
            parent,
            width=width,
            height=height,
            bg=ModernStyle.PANEL_BG,
            highlightthickness=0,
            bd=2,
            relief=tk.SUNKEN,
        )
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)

        self._rects = {}
        self._draw()

    def pack(self, **kwargs):
        self.canvas.pack(**kwargs)

    def _draw(self):
        for hour in range(0, 24, 3):
            self.canvas.create_text(
                self.label_width + hour * self.cell_width + 1,
                self.header_height // 2,
                text=str(hour),
                anchor="w",
                font=ModernStyle.FONT_SMALL,
                fill=ModernStyle.TEXT_DIM,
            )

        for day_index, day_code in enumerate(DAY_ORDER):
            top = self.header_height + day_index * self.cell_height
            self.canvas.create_text(
                2,
                top + self.cell_height // 2,
                text=DAY_LABELS[day_code],
                anchor="w",
                font=ModernStyle.FONT_SMALL,
                fill=ModernStyle.TEXT,
            )

            for hour in range(24):
                left = self.label_width + hour * self.cell_width
                rect = self.canvas.create_rectangle(
                    left,
                    top,
                    left + self.cell_width,
                    top + self.cell_height,
                    outline=ModernStyle.BORDER_SHADOW,
                    width=1,
                )
                self._rects[(day_index, hour)] = rect

        self.refresh()

    def refresh(self):
        for key, rect in self._rects.items():
            active = key in self.cells
            self.canvas.itemconfigure(
                rect,
                fill=ModernStyle.SELECT_BG if active else ModernStyle.FIELD_BG,
            )

    def _cell_at(self, x, y):
        if x < self.label_width or y < self.header_height:
            return None
        hour = int((x - self.label_width) // self.cell_width)
        day_index = int((y - self.header_height) // self.cell_height)
        if 0 <= hour < 24 and 0 <= day_index < 7:
            return (day_index, hour)
        return None

    def _on_press(self, event):
        cell = self._cell_at(event.x, event.y)
        if cell is None:
            return
        # Dragging continues whatever the first cell did, so a drag either
        # paints or erases rather than flip-flopping under the cursor.
        self._paint_value = cell not in self.cells
        self._apply(cell)

    def _on_drag(self, event):
        cell = self._cell_at(event.x, event.y)
        if cell is not None:
            self._apply(cell)

    def _apply(self, cell):
        already = cell in self.cells
        if self._paint_value == already:
            return
        if self._paint_value:
            self.cells.add(cell)
        else:
            self.cells.discard(cell)
        self.canvas.itemconfigure(
            self._rects[cell],
            fill=ModernStyle.SELECT_BG if self._paint_value else ModernStyle.FIELD_BG,
        )
        self.on_change()

    def set_cells(self, cells):
        self.cells = set(cells)
        self.refresh()


class SettingsWindow:
    WINDOW_WIDTH = 640
    WINDOW_HEIGHT = 580
    MIN_WINDOW_HEIGHT = 460
    WINDOW_MARGIN = 80

    TABS = ("Status", "Activity", "Schedule", "Startup", "About")

    # Class-level default so the save logic is safe to reason about even
    # before the widgets that drive the flag exist.
    _grid_dirty = False

    def __init__(self, app):
        self.app = app
        self.window = None
        self.is_open = False
        self._icon_photo = None
        self.draft_windows = []
        self.grid_cells = set()
        self.grid = None
        self._grid_dirty = False
        self._tab_frames = {}
        self._tab_buttons = {}
        self._active_tab = self.TABS[0]
        self._status_message = ""

    @classmethod
    def calculate_window_geometry(cls, screen_width, screen_height, scale=1.0):
        """Window size in physical pixels.

        With DPI awareness on, screen dimensions arrive in physical pixels and
        Tk grows the fonts, so the pixel constants have to grow with them or
        the content no longer fits.
        """
        scale = max(1.0, min(3.0, float(scale)))
        width = min(round(cls.WINDOW_WIDTH * scale), max(round(480 * scale), screen_width - cls.WINDOW_MARGIN))
        available_height = max(round(cls.MIN_WINDOW_HEIGHT * scale), screen_height - cls.WINDOW_MARGIN)
        height = min(round(cls.WINDOW_HEIGHT * scale), available_height)
        x_pos = max(0, (screen_width - width) // 2)
        y_pos = max(0, (screen_height - height) // 2)
        return width, height, x_pos, y_pos

    def build_schedule_windows_for_save(self):
        """Windows to persist.

        The grid has hour resolution, so an untouched grid must not overwrite a
        schedule that was configured with minute precision.
        """
        if self._grid_dirty:
            return grid_to_windows(self.grid_cells)
        return [TimeWindow(**window.to_dict()) for window in self.draft_windows]

    # ------------------------------------------------------------------ setup

    def show(self):
        if self.window and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            self.window.focus_force()
            return

        self.draft_windows = [TimeWindow(**window.to_dict()) for window in self.app.config.schedule.windows]
        self.grid_cells = windows_to_grid(self.draft_windows)
        self._grid_dirty = False

        parent = self.app.root if self.app.root else None
        self.window = tk.Toplevel(parent) if parent else tk.Tk()
        self.window.title("{0} - Settings".format(APP_NAME))
        self.window.configure(bg=ModernStyle.WINDOW_BG)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        self.is_open = True

        self.window.update_idletasks()
        scale = getattr(self.app, "display_scaling", 1.0)
        width, height, x_pos, y_pos = self.calculate_window_geometry(
            self.window.winfo_screenwidth(),
            self.window.winfo_screenheight(),
            scale,
        )
        self.window.minsize(round(480 * scale), round(self.MIN_WINDOW_HEIGHT * scale))
        self.window.resizable(True, True)
        self.window.geometry("{0}x{1}+{2}+{3}".format(width, height, x_pos, y_pos))

        if ICON_FILE.exists():
            try:
                self._icon_photo = tk.PhotoImage(file=str(ICON_FILE))
                self.window.iconphoto(True, self._icon_photo)
            except Exception:
                self.app.logger.debug("Could not set Tk icon", exc_info=True)

        self._create_ui()
        self._select_tab(self._active_tab)
        self._refresh_runtime_display()

        self.window.bind("<Return>", lambda event: self._save_settings())
        self.window.bind("<Escape>", lambda event: self._on_close())
        self.window.focus_force()

    def _create_ui(self):
        shell = tk.Frame(self.window, bg=ModernStyle.WINDOW_BG)
        shell.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self._create_header(shell)

        tab_bar = tk.Frame(shell, bg=ModernStyle.WINDOW_BG)
        tab_bar.pack(fill=tk.X, pady=(10, 0))
        for name in self.TABS:
            button = tk.Label(
                tab_bar,
                text=name,
                font=ModernStyle.FONT_BODY,
                fg=ModernStyle.TEXT,
                bg=ModernStyle.PANEL_BG,
                bd=2,
                relief=tk.RAISED,
                padx=12,
                pady=4,
                cursor="hand2",
            )
            button.pack(side=tk.LEFT, padx=(0, 2))
            button.bind("<Button-1>", lambda event, tab=name: self._select_tab(tab))
            self._tab_buttons[name] = button

        body = tk.Frame(shell, bg=ModernStyle.PANEL_BG, bd=2, relief=tk.RAISED)
        body.pack(fill=tk.BOTH, expand=True)

        for name in self.TABS:
            frame = tk.Frame(body, bg=ModernStyle.PANEL_BG)
            self._tab_frames[name] = frame

        self._build_status_tab(self._tab_frames["Status"])
        self._build_activity_tab(self._tab_frames["Activity"])
        self._build_schedule_tab(self._tab_frames["Schedule"])
        self._build_startup_tab(self._tab_frames["Startup"])
        self._build_about_tab(self._tab_frames["About"])

        self._create_footer(shell)

    def _create_header(self, parent):
        header = tk.Frame(parent, bg=ModernStyle.TITLE_BG, bd=2, relief=tk.RAISED)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text=APP_NAME,
            font=ModernStyle.FONT_BODY_BOLD,
            fg=ModernStyle.TITLE_TEXT,
            bg=ModernStyle.TITLE_BG,
            padx=8,
            pady=4,
        ).pack(side=tk.LEFT)

        self.header_status_label = tk.Label(
            header,
            text="",
            font=ModernStyle.FONT_SMALL,
            fg=ModernStyle.TITLE_TEXT,
            bg=ModernStyle.TITLE_BG,
            padx=8,
        )
        self.header_status_label.pack(side=tk.RIGHT)

    def _create_footer(self, parent):
        footer = tk.Frame(parent, bg=ModernStyle.WINDOW_BG)
        footer.pack(fill=tk.X, pady=(8, 0))

        buttons = tk.Frame(footer, bg=ModernStyle.WINDOW_BG)
        buttons.pack(side=tk.RIGHT)
        self._create_button(buttons, "Close", self._on_close).pack(side=tk.RIGHT, padx=(6, 0))
        self._create_button(buttons, "Save", self._save_settings, primary=True).pack(side=tk.RIGHT)

        # A status bar rather than a modal box on every save: less interrupting
        # and considerably more period-correct.
        self.status_bar = tk.Label(
            footer,
            text="",
            font=ModernStyle.FONT_SMALL,
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.PANEL_BG,
            bd=2,
            relief=tk.SUNKEN,
            anchor="w",
            padx=6,
            pady=2,
        )
        self.status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _select_tab(self, name):
        self._active_tab = name
        for tab_name, button in self._tab_buttons.items():
            selected = tab_name == name
            button.config(
                relief=tk.SUNKEN if selected else tk.RAISED,
                bg=ModernStyle.PANEL_INNER if selected else ModernStyle.PANEL_BG,
                font=ModernStyle.FONT_BODY_BOLD if selected else ModernStyle.FONT_BODY,
            )
        for tab_name, frame in self._tab_frames.items():
            if tab_name == name:
                frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
            else:
                frame.pack_forget()

    # ------------------------------------------------------------------- tabs

    def _build_status_tab(self, parent):
        status_row = tk.Frame(parent, bg=ModernStyle.PANEL_BG)
        status_row.pack(fill=tk.X)

        self.status_indicator = tk.Label(status_row, text="■", font=ModernStyle.FONT_BODY_BOLD, bg=ModernStyle.PANEL_BG)
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
            parent,
            text="",
            font=ModernStyle.FONT_SMALL,
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.PANEL_BG,
            anchor="w",
            justify=tk.LEFT,
            wraplength=540,
        )
        self.status_detail_label.pack(fill=tk.X, pady=(8, 0))

        self._separator(parent)

        stats = tk.Frame(parent, bg=ModernStyle.PANEL_BG)
        stats.pack(fill=tk.X)

        self.session_label = self._stat_label(stats, "Session: 00:00:00", tk.LEFT)
        self.activity_label = self._stat_label(stats, "Session activities: 0", tk.RIGHT)

        totals = tk.Frame(parent, bg=ModernStyle.PANEL_BG)
        totals.pack(fill=tk.X, pady=(6, 0))

        self.total_activity_label = self._stat_label(totals, "Lifetime activities: 0", tk.LEFT)
        self.last_activity_label = self._stat_label(totals, "Last activity: --", tk.RIGHT)

        self._separator(parent)

        self.startup_status_label = tk.Label(
            parent,
            text="",
            font=ModernStyle.FONT_SMALL,
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.PANEL_BG,
            anchor="w",
            justify=tk.LEFT,
            wraplength=540,
        )
        self.startup_status_label.pack(fill=tk.X)

    def _build_activity_tab(self, parent):
        self.preset_var = tk.StringVar(value=self.app.config.profile_name)
        self._create_option_row(parent, "Preset", self.preset_var, list(PRESET_CONFIGS.keys()), self._apply_preset)

        self.interval_var = tk.StringVar(value=str(self.app.config.interval))
        self._create_entry_row(parent, "Activity Interval", self.interval_var, "seconds")

        self.activity_type_var = tk.StringVar(value=self.app.config.activity_type)
        self._create_option_row(parent, "Activity Type", self.activity_type_var, VALID_ACTIVITY_TYPES)

        self.zen_jiggle_var = tk.BooleanVar(value=self.app.config.zen_jiggle)
        self._create_toggle_row(parent, "Invisible Mouse Jiggle", self.zen_jiggle_var)

        self._separator(parent)

        tk.Label(
            parent,
            text=(
                "Keep Awake uses the Windows power API directly, so it needs no "
                "simulated input. On a managed PC a lock screen enforced by "
                "company policy still applies."
            ),
            font=ModernStyle.FONT_SMALL,
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.PANEL_BG,
            anchor="w",
            justify=tk.LEFT,
            wraplength=540,
        ).pack(fill=tk.X, pady=(0, 4))

        self.prevent_sleep_var = tk.BooleanVar(value=self.app.config.prevent_sleep)
        self._create_toggle_row(parent, "Prevent Sleep", self.prevent_sleep_var)

        self.keep_display_var = tk.BooleanVar(value=self.app.config.keep_display_on)
        self._create_toggle_row(parent, "Keep Screen On", self.keep_display_var)

        self.idle_aware_var = tk.BooleanVar(value=self.app.config.idle_aware)
        self._create_toggle_row(parent, "Only Act While You Are Away", self.idle_aware_var)

        self.idle_threshold_var = tk.StringVar(value=str(self.app.config.idle_threshold))
        self._create_entry_row(parent, "Consider Away After", self.idle_threshold_var, "seconds")

    def _build_startup_tab(self, parent):
        self.startup_var = tk.BooleanVar(value=self.app.is_startup_enabled())
        self._create_toggle_row(parent, "Start with Windows", self.startup_var)

        self.minimized_var = tk.BooleanVar(value=self.app.config.start_minimized)
        self._create_toggle_row(parent, "Start Minimized", self.minimized_var)

        self.notifications_var = tk.BooleanVar(value=self.app.config.notifications_enabled)
        self._create_toggle_row(parent, "Notifications", self.notifications_var)

        self._separator(parent)

        self.startup_detail_label = tk.Label(
            parent,
            text="",
            font=ModernStyle.FONT_SMALL,
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.PANEL_BG,
            anchor="w",
            justify=tk.LEFT,
            wraplength=540,
        )
        self.startup_detail_label.pack(fill=tk.X)

        tk.Label(
            parent,
            text=(
                "A Scheduled Task is registered first, because Run key entries can "
                "be switched off from Task Manager's Startup tab. If policy blocks "
                "that, the Run key is used instead.\n\n"
                "The entry is checked on every launch, so moving this folder or "
                "reinstalling Python repairs it rather than silently breaking it."
            ),
            font=ModernStyle.FONT_SMALL,
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.PANEL_BG,
            anchor="w",
            justify=tk.LEFT,
            wraplength=540,
        ).pack(fill=tk.X, pady=(10, 0))

    def _build_schedule_tab(self, parent):
        self.schedule_enabled_var = tk.BooleanVar(value=self.app.config.schedule.enabled)
        self._create_toggle_row(parent, "Enable Schedule", self.schedule_enabled_var, command=self._update_schedule_preview)

        tk.Label(
            parent,
            text="Click or drag to choose the hours you want to appear active.",
            font=ModernStyle.FONT_SMALL,
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.PANEL_BG,
            anchor="w",
        ).pack(fill=tk.X, pady=(4, 6))

        grid_holder = tk.Frame(parent, bg=ModernStyle.PANEL_BG)
        grid_holder.pack(fill=tk.X)
        self.grid = ScheduleGrid(grid_holder, self.grid_cells, self._on_grid_change)
        self.grid.pack(anchor="w")

        quick = tk.Frame(parent, bg=ModernStyle.PANEL_BG)
        quick.pack(fill=tk.X, pady=(8, 0))
        self._create_button(quick, "Work hours", lambda: self._fill_grid("work")).pack(side=tk.LEFT, padx=(0, 6))
        self._create_button(quick, "All day", lambda: self._fill_grid("all")).pack(side=tk.LEFT, padx=(0, 6))
        self._create_button(quick, "Clear", lambda: self._fill_grid("none")).pack(side=tk.LEFT)

        self.precision_label = tk.Label(
            parent,
            text="",
            font=ModernStyle.FONT_SMALL,
            fg=ModernStyle.WARNING,
            bg=ModernStyle.PANEL_BG,
            anchor="w",
            justify=tk.LEFT,
            wraplength=540,
        )
        self.precision_label.pack(fill=tk.X, pady=(8, 0))
        if schedule_uses_minute_precision(self.draft_windows):
            self.precision_label.config(
                text=(
                    "This schedule uses minute precision. The grid works in whole "
                    "hours, so editing it will round your windows."
                )
            )

        self.schedule_preview_label = tk.Label(
            parent,
            text="",
            font=ModernStyle.FONT_SMALL,
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.PANEL_BG,
            anchor="w",
            justify=tk.LEFT,
            wraplength=540,
        )
        self.schedule_preview_label.pack(fill=tk.X, pady=(6, 0))

    def _build_about_tab(self, parent):
        tk.Label(
            parent,
            text=APP_NAME,
            font=ModernStyle.FONT_TITLE,
            fg=ModernStyle.TEXT,
            bg=ModernStyle.PANEL_BG,
        ).pack(anchor="w")

        tk.Label(
            parent,
            text="Keeps your PC awake and your Teams status green.",
            font=ModernStyle.FONT_SUBTITLE,
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.PANEL_BG,
        ).pack(anchor="w", pady=(0, 10))

        self._separator(parent)

        for line in (
            "What it does:",
            "  - Asks Windows not to sleep, through the supported power API.",
            "  - Sends an F15 keypress, which no application reacts to, so Teams",
            "    sees activity and stops marking you Away.",
            "  - Only acts once you have genuinely been idle.",
            "",
            "What it does not do:",
            "  - Hide anything from your employer. This is an ordinary tray app.",
            "  - Override a lock screen enforced by company policy.",
            "  - Send data anywhere. There is no network code in this project.",
        ):
            tk.Label(
                parent,
                text=line,
                font=ModernStyle.FONT_SMALL,
                fg=ModernStyle.TEXT if line.endswith(":") else ModernStyle.TEXT_DIM,
                bg=ModernStyle.PANEL_BG,
                anchor="w",
                justify=tk.LEFT,
            ).pack(fill=tk.X)

        self._separator(parent)

        tk.Label(
            parent,
            text="Logs: {0}".format(LOG_DIR),
            font=ModernStyle.FONT_SMALL,
            fg=ModernStyle.TEXT_DIM,
            bg=ModernStyle.PANEL_BG,
            anchor="w",
            justify=tk.LEFT,
            wraplength=540,
        ).pack(fill=tk.X)

    # -------------------------------------------------------------- utilities

    def _separator(self, parent):
        holder = tk.Frame(parent, bg=ModernStyle.PANEL_BG)
        holder.pack(fill=tk.X, pady=10)
        tk.Frame(holder, bg=ModernStyle.BORDER_SHADOW, height=1).pack(fill=tk.X)
        tk.Frame(holder, bg=ModernStyle.BORDER_HIGHLIGHT, height=1).pack(fill=tk.X)

    def _stat_label(self, parent, text, side):
        label = tk.Label(parent, text=text, font=ModernStyle.FONT_SMALL, fg=ModernStyle.TEXT_DIM, bg=ModernStyle.PANEL_BG)
        label.pack(side=side)
        return label

    def _create_button(self, parent, text, command, primary=False):
        button = tk.Button(
            parent,
            text=text,
            font=ModernStyle.FONT_BODY_BOLD if primary else ModernStyle.FONT_BODY,
            bg=ModernStyle.PANEL_BG,
            fg=ModernStyle.TEXT,
            activebackground=ModernStyle.PANEL_INNER,
            activeforeground=ModernStyle.TEXT,
            relief=tk.RAISED,
            bd=2,
            highlightbackground=ModernStyle.PANEL_BG,
            highlightthickness=1,
            takefocus=True,
            command=command,
        )
        button.config(padx=12, pady=3)
        # Explicit press states: a Win95 button visibly sinks, and Tk's default
        # only does so on some platforms.
        button.bind("<ButtonPress-1>", lambda event: event.widget.config(relief=tk.SUNKEN))
        button.bind("<ButtonRelease-1>", lambda event: event.widget.config(relief=tk.RAISED))
        button.bind("<FocusIn>", lambda event: event.widget.config(highlightbackground=ModernStyle.TEXT))
        button.bind("<FocusOut>", lambda event: event.widget.config(highlightbackground=ModernStyle.PANEL_BG))
        return button

    def _create_entry_row(self, parent, label_text, variable, suffix):
        row = tk.Frame(parent, bg=ModernStyle.PANEL_BG)
        row.pack(fill=tk.X, pady=6)
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
        entry.pack(side=tk.LEFT, padx=(0, 5), ipady=2)
        tk.Label(right, text=suffix, font=ModernStyle.FONT_BODY, fg=ModernStyle.TEXT_DIM, bg=ModernStyle.PANEL_BG).pack(side=tk.LEFT)

    def _create_option_row(self, parent, label_text, variable, options, command=None):
        row = tk.Frame(parent, bg=ModernStyle.PANEL_BG)
        row.pack(fill=tk.X, pady=6)
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

    def _create_toggle_row(self, parent, label_text, variable, command=None):
        row = tk.Frame(parent, bg=ModernStyle.PANEL_BG)
        row.pack(fill=tk.X, pady=6)
        tk.Label(row, text=label_text, font=ModernStyle.FONT_BODY, fg=ModernStyle.TEXT, bg=ModernStyle.PANEL_BG).pack(side=tk.LEFT)
        toggle = tk.Checkbutton(
            row,
            variable=variable,
            text="",
            bg=ModernStyle.PANEL_BG,
            fg=ModernStyle.TEXT,
            activebackground=ModernStyle.PANEL_BG,
            activeforeground=ModernStyle.TEXT,
            selectcolor=ModernStyle.FIELD_BG,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=ModernStyle.PANEL_BG,
            font=ModernStyle.FONT_BODY,
            command=command,
        )
        toggle.pack(side=tk.RIGHT)

    # --------------------------------------------------------------- schedule

    def _on_grid_change(self):
        self._grid_dirty = True
        self.grid_cells = self.grid.cells
        self._update_schedule_preview()

    def _fill_grid(self, mode):
        if mode == "all":
            cells = {(day, hour) for day in range(7) for hour in range(24)}
        elif mode == "work":
            cells = {(day, hour) for day in range(5) for hour in range(9, 18)}
        else:
            cells = set()

        self.grid.set_cells(cells)
        self.grid_cells = self.grid.cells
        self._grid_dirty = True
        self._update_schedule_preview()

    def _apply_preset(self, preset_name):
        preview_config = self.app.config.clone()
        apply_preset(preview_config, preset_name)
        self.interval_var.set(str(preview_config.interval))
        self.activity_type_var.set(preview_config.activity_type)
        self.schedule_enabled_var.set(preview_config.schedule.enabled)
        self.draft_windows = [TimeWindow(**window.to_dict()) for window in preview_config.schedule.windows]
        self.grid_cells = windows_to_grid(self.draft_windows)
        if self.grid:
            self.grid.set_cells(self.grid_cells)
        # The preset defines the windows exactly, so the grid is authoritative
        # only once the user edits it again.
        self._grid_dirty = False
        self._update_schedule_preview()
        self._set_status("Preset '{0}' loaded. Press Save to apply.".format(preset_name))

    def _update_schedule_preview(self):
        if not hasattr(self, "schedule_preview_label"):
            return
        windows = self.build_schedule_windows_for_save()
        preview = ScheduleConfig(enabled=self.schedule_enabled_var.get(), windows=windows)
        self.schedule_preview_label.config(text=describe_schedule(preview))

    # ---------------------------------------------------------------- runtime

    def _toggle_status(self):
        self.app.toggle_state()
        self._refresh_runtime_display()

    def _set_status(self, message):
        self._status_message = message
        if hasattr(self, "status_bar"):
            try:
                self.status_bar.config(text=message)
            except tk.TclError:
                pass

    def _refresh_runtime_display(self):
        if not self.window or not self.window.winfo_exists():
            self.is_open = False
            return

        try:
            status_name, color, detail = self.app.get_status_presentation()
            self.status_indicator.config(fg=color)
            self.status_label.config(text=status_name)
            self.status_detail_label.config(text=detail)
            self.header_status_label.config(text=status_name)
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

            self._refresh_startup_display()
            self._update_schedule_preview()
            self.window.after(1000, self._refresh_runtime_display)
        except tk.TclError:
            self.is_open = False

    def _refresh_startup_display(self):
        status = self.app.get_startup_status()
        color = ModernStyle.TEXT_DIM
        if status.enabled and not status.healthy:
            color = ModernStyle.WARNING
        elif status.enabled:
            color = ModernStyle.SUCCESS
        self.startup_status_label.config(
            text="Startup: {0} - {1}".format(status.label(), status.detail),
            fg=color,
        )
        if hasattr(self, "startup_detail_label"):
            lines = ["Current registration: {0}".format(status.label()), status.detail]
            if status.command:
                lines.append(status.command)
            self.startup_detail_label.config(text="\n".join(lines), fg=color)

    # ------------------------------------------------------------------- save

    def _save_settings(self):
        try:
            raw_interval = self.interval_var.get().strip()
            interval = clamp_interval(raw_interval)
            if str(interval) != raw_interval:
                raise ValueError("Interval must be between 10 and 300 seconds.")

            activity_type = self.activity_type_var.get()
            if activity_type not in VALID_ACTIVITY_TYPES:
                raise ValueError("Select a valid activity type.")

            raw_threshold = self.idle_threshold_var.get().strip()
            idle_threshold = clamp_idle_threshold(raw_threshold)
            if str(idle_threshold) != raw_threshold:
                raise ValueError("Away threshold must be between 10 and 600 seconds.")

            schedule_windows = self.build_schedule_windows_for_save()
            if self.schedule_enabled_var.get() and not schedule_windows:
                raise ValueError("Select at least one hour in the schedule grid, or turn the schedule off.")

            updated_config = self.app.config.clone()
            updated_config.interval = interval
            updated_config.activity_type = activity_type
            updated_config.start_minimized = self.minimized_var.get()
            updated_config.notifications_enabled = self.notifications_var.get()
            updated_config.prevent_sleep = self.prevent_sleep_var.get()
            updated_config.keep_display_on = self.keep_display_var.get()
            updated_config.idle_aware = self.idle_aware_var.get()
            updated_config.idle_threshold = idle_threshold
            updated_config.zen_jiggle = self.zen_jiggle_var.get()
            updated_config.profile_name = self.preset_var.get() if self.preset_var.get() in PRESET_CONFIGS else "Custom"
            updated_config.schedule = ScheduleConfig(
                enabled=self.schedule_enabled_var.get(),
                windows=schedule_windows,
            )

            # Apply the config first: it is the part that cannot fail, so a
            # registry problem below can no longer discard the user's edits.
            self.app.apply_config(updated_config)
            self.draft_windows = [TimeWindow(**window.to_dict()) for window in updated_config.schedule.windows]
            self.grid_cells = windows_to_grid(self.draft_windows)
            if self.grid:
                self.grid.set_cells(self.grid_cells)
            self._grid_dirty = False
            self.precision_label.config(text="")
        except ValueError as error:
            self._set_status(str(error))
            messagebox.showerror("Error", str(error))
            return
        except Exception as error:
            self.app.logger.exception("Could not save settings")
            self._set_status("Could not save settings.")
            messagebox.showerror("Error", "Could not save settings:\n{0}".format(error))
            return

        saved_at = self.app.now_provider().strftime("%H:%M")
        try:
            self.app.set_startup_enabled(self.startup_var.get())
        except Exception as error:
            self.app.logger.exception("Could not update startup registration")
            self._set_status("Settings saved, but Windows startup could not be updated.")
            messagebox.showwarning(
                "Startup not changed",
                "Your settings were saved, but Windows startup could not be updated:\n\n{0}".format(error),
            )
            self.startup_var.set(self.app.is_startup_enabled())
            return

        self._set_status("Settings saved - {0}".format(saved_at))

    def _on_close(self):
        self.is_open = False
        if self.window:
            self.window.destroy()
