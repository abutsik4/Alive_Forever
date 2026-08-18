"""Scheduling primitives and evaluation helpers."""

from dataclasses import dataclass, field
from datetime import datetime, time as dt_time, timedelta
from typing import List


DAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_LABELS = {
    "mon": "Mon",
    "tue": "Tue",
    "wed": "Wed",
    "thu": "Thu",
    "fri": "Fri",
    "sat": "Sat",
    "sun": "Sun",
}


def parse_time_string(value):
    if not isinstance(value, str):
        raise ValueError("Time must be in HH:MM format")

    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError("Time must be in HH:MM format")

    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("Time must be in HH:MM format")
    return dt_time(hour=hour, minute=minute)


def sanitize_days(days):
    if not isinstance(days, list):
        return list(DAY_ORDER)

    normalized = []
    for day in days:
        if isinstance(day, str):
            short_day = day.strip().lower()[:3]
            if short_day in DAY_ORDER and short_day not in normalized:
                normalized.append(short_day)
    return normalized or list(DAY_ORDER)


def day_code_for_date(value):
    return DAY_ORDER[value.weekday()]


@dataclass
class TimeWindow:
    start: str
    end: str
    days: List[str] = field(default_factory=lambda: list(DAY_ORDER))

    def __post_init__(self):
        parse_time_string(self.start)
        parse_time_string(self.end)
        if self.start == self.end:
            raise ValueError("Schedule windows need different start and end times.")
        self.days = sanitize_days(self.days)

    def label(self):
        day_text = ", ".join(DAY_LABELS[day] for day in self.days)
        return "{0} | {1}-{2}".format(day_text, self.start, self.end)

    def to_dict(self):
        return {
            "start": self.start,
            "end": self.end,
            "days": list(self.days),
        }


@dataclass
class ScheduleConfig:
    enabled: bool = False
    windows: List[TimeWindow] = field(default_factory=list)

    @classmethod
    def default(cls):
        return cls(
            enabled=False,
            windows=[TimeWindow(start="09:00", end="17:00", days=["mon", "tue", "wed", "thu", "fri"])],
        )

    @classmethod
    def from_raw(cls, raw_schedule):
        if not isinstance(raw_schedule, dict):
            return cls.default()

        enabled = bool(raw_schedule.get("enabled", False))
        windows = []

        raw_windows = raw_schedule.get("windows")
        if isinstance(raw_windows, list):
            for raw_window in raw_windows:
                if not isinstance(raw_window, dict):
                    continue
                try:
                    windows.append(
                        TimeWindow(
                            start=raw_window.get("start", "09:00"),
                            end=raw_window.get("end", "17:00"),
                            days=raw_window.get("days", list(DAY_ORDER)),
                        )
                    )
                except ValueError:
                    continue
        elif {"start", "end"}.intersection(raw_schedule.keys()):
            try:
                windows.append(
                    TimeWindow(
                        start=raw_schedule.get("start", "09:00"),
                        end=raw_schedule.get("end", "17:00"),
                        days=raw_schedule.get("days", list(DAY_ORDER)),
                    )
                )
            except ValueError:
                windows = []

        if not windows:
            windows = cls.default().windows

        return cls(enabled=enabled, windows=windows)

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "windows": [window.to_dict() for window in self.windows],
        }

    def clone(self):
        return ScheduleConfig(enabled=self.enabled, windows=[TimeWindow(**window.to_dict()) for window in self.windows])


def build_window_occurrence(window, active_date):
    start_time = parse_time_string(window.start)
    end_time = parse_time_string(window.end)
    start_at = datetime.combine(active_date, start_time)
    end_at = datetime.combine(active_date, end_time)
    if start_time >= end_time:
        end_at += timedelta(days=1)
    return start_at, end_at


def iter_window_occurrences(schedule, now, day_span=14):
    for offset in range(-1, day_span):
        active_date = (now + timedelta(days=offset)).date()
        active_day = day_code_for_date(active_date)
        for window in schedule.windows:
            if active_day not in window.days:
                continue
            yield window, build_window_occurrence(window, active_date)


def is_schedule_active(schedule, now=None):
    if now is None:
        now = datetime.now()

    if not schedule.enabled:
        return True

    for _, (start_at, end_at) in iter_window_occurrences(schedule, now, day_span=2):
        if start_at <= now < end_at:
            return True
    return False


def get_next_transition(schedule, now=None):
    if now is None:
        now = datetime.now()

    if not schedule.enabled:
        return None

    candidates = []
    for _, (start_at, end_at) in iter_window_occurrences(schedule, now, day_span=14):
        if start_at > now:
            candidates.append(("active", start_at))
        if end_at > now:
            candidates.append(("scheduled_off", end_at))

    if not candidates:
        return None
    return min(candidates, key=lambda item: item[1])


def format_transition(transition):
    if not transition:
        return ""

    next_state, transition_at = transition
    label = "Active" if next_state == "active" else "Scheduled Off"
    return "Next: {0} at {1}".format(label, transition_at.strftime("%a %H:%M"))


def _covered_hours(start_time, end_time):
    """Hour slots [0, 24) touched by a window that does not cross midnight."""
    last_hour = end_time.hour - 1 if end_time.minute == 0 else end_time.hour
    return list(range(start_time.hour, min(last_hour, 23) + 1))


def windows_to_grid(windows):
    """Project time windows onto a 7x24 set of (day_index, hour) cells.

    The grid has hour resolution, so a window like 08:30-11:45 lights up 08
    through 11. Callers must therefore only write the grid back when the user
    actually edited it, or minute-level schedules would be silently rounded.
    """
    cells = set()
    for window in windows:
        start_time = parse_time_string(window.start)
        end_time = parse_time_string(window.end)

        for day in window.days:
            day_index = DAY_ORDER.index(day)

            if start_time < end_time:
                for hour in _covered_hours(start_time, end_time):
                    cells.add((day_index, hour))
                continue

            # Crosses midnight: fill to the end of this day, then spill into
            # the next one.
            for hour in range(start_time.hour, 24):
                cells.add((day_index, hour))
            next_day = (day_index + 1) % 7
            last_hour = end_time.hour - 1 if end_time.minute == 0 else end_time.hour
            for hour in range(0, min(last_hour, 23) + 1):
                cells.add((next_day, hour))
    return cells


def _runs_for_day(hours):
    """Contiguous (start, end_exclusive) hour runs from a sorted hour list."""
    runs = []
    for hour in sorted(hours):
        if runs and runs[-1][1] == hour:
            runs[-1][1] = hour + 1
        else:
            runs.append([hour, hour + 1])
    return [tuple(run) for run in runs]


def _format_hour(hour):
    if hour >= 24:
        # 24:00 is not expressible, and 00:00 would equal the start of a
        # full-day run, so clamp to the last minute of the day.
        return "23:59"
    return "{0:02d}:00".format(hour)


def grid_to_windows(cells):
    """Collapse grid cells back into the smallest set of time windows.

    Days sharing an identical run are merged into one window, which keeps the
    saved schedule readable instead of producing seven near-identical entries.
    """
    runs_by_day = {}
    for day_index in range(7):
        hours = [hour for (day, hour) in cells if day == day_index]
        if hours:
            runs_by_day[day_index] = _runs_for_day(hours)

    days_by_run = {}
    for day_index, runs in sorted(runs_by_day.items()):
        for run in runs:
            days_by_run.setdefault(run, []).append(DAY_ORDER[day_index])

    windows = []
    for (start_hour, end_hour), days in sorted(days_by_run.items()):
        start = _format_hour(start_hour)
        end = _format_hour(end_hour)
        if start == end:
            continue
        windows.append(TimeWindow(start=start, end=end, days=days))
    return windows


def schedule_uses_minute_precision(windows):
    """True when rounding to the grid's hour resolution would lose detail."""
    for window in windows:
        if parse_time_string(window.start).minute or parse_time_string(window.end).minute:
            return True
    return False


def describe_schedule(schedule, now=None):
    if not schedule.enabled:
        return "Schedule disabled. The app stays active unless you pause it manually."

    window_labels = [window.label() for window in schedule.windows]
    if not window_labels:
        return "Schedule enabled, but no windows are configured."

    summary = "; ".join(window_labels[:3])
    if len(window_labels) > 3:
        summary = "{0}; +{1} more".format(summary, len(window_labels) - 3)

    transition = format_transition(get_next_transition(schedule, now=now))
    if transition:
        return "{0}. {1}".format(summary, transition)
    return summary