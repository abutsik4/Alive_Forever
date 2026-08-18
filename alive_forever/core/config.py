"""Application configuration loading, migration, and presets."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from alive_forever.core.scheduler import ScheduleConfig, TimeWindow
from alive_forever.system.windows import (
    CONFIG_FILE,
    LEGACY_CONFIG_FILE,
    ensure_app_directories,
    write_json_atomic,
)


VALID_ACTIVITY_TYPES = ["F15 Key (Recommended)", "Mouse Jiggle", "Both"]
PRESET_CONFIGS = {
    "Custom": None,
    "Always On": {
        "interval": 60,
        "activity_type": "F15 Key (Recommended)",
        "schedule": ScheduleConfig.default(),
    },
    "Workday": {
        "interval": 60,
        "activity_type": "F15 Key (Recommended)",
        "schedule": ScheduleConfig(
            enabled=True,
            windows=[
                TimeWindow(start="09:00", end="12:00", days=["mon", "tue", "wed", "thu", "fri"]),
                TimeWindow(start="13:00", end="18:00", days=["mon", "tue", "wed", "thu", "fri"]),
            ],
        ),
    },
    "Evening": {
        "interval": 120,
        "activity_type": "F15 Key (Recommended)",
        "schedule": ScheduleConfig(
            enabled=True,
            windows=[TimeWindow(start="18:00", end="23:30", days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"])],
        ),
    },
    "Stealth": {
        "interval": 90,
        "activity_type": "Both",
        "schedule": ScheduleConfig(
            enabled=True,
            windows=[
                TimeWindow(start="08:30", end="11:45", days=["mon", "tue", "wed", "thu", "fri"]),
                TimeWindow(start="12:30", end="17:30", days=["mon", "tue", "wed", "thu", "fri"]),
            ],
        ),
    },
}


VALID_OVERRIDE_STATES = ("active", "paused")


def clamp_interval(value):
    try:
        interval = int(value)
    except (TypeError, ValueError):
        return 60
    return max(10, min(300, interval))


def clamp_idle_threshold(value):
    try:
        threshold = int(value)
    except (TypeError, ValueError):
        return 45
    return max(10, min(600, threshold))


def parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass
class AppConfig:
    interval: int = 60
    activity_type: str = "F15 Key (Recommended)"
    start_minimized: bool = True
    notifications_enabled: bool = True
    profile_name: str = "Custom"
    first_run_completed: bool = False

    # Keep-awake is handled by Windows' own power API rather than by faking
    # input, so it works even while the app is injecting nothing at all.
    prevent_sleep: bool = True
    keep_display_on: bool = False

    # Only inject when the user is genuinely away, so we never fight them for
    # the keyboard or the cursor.
    idle_aware: bool = True
    idle_threshold: int = 45

    # Zero-pixel mouse movement: counts as input, never moves the pointer.
    zen_jiggle: bool = True

    # Temporary "stay active until" / "pause until" set from the tray.
    override_state: Optional[str] = None
    override_until: Optional[datetime] = None

    lifetime_activity_count: int = 0
    last_activity_at: Optional[datetime] = None
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig.default)

    def clone(self):
        return AppConfig(
            interval=self.interval,
            activity_type=self.activity_type,
            start_minimized=self.start_minimized,
            notifications_enabled=self.notifications_enabled,
            profile_name=self.profile_name,
            first_run_completed=self.first_run_completed,
            prevent_sleep=self.prevent_sleep,
            keep_display_on=self.keep_display_on,
            idle_aware=self.idle_aware,
            idle_threshold=self.idle_threshold,
            zen_jiggle=self.zen_jiggle,
            override_state=self.override_state,
            override_until=self.override_until,
            lifetime_activity_count=self.lifetime_activity_count,
            last_activity_at=self.last_activity_at,
            schedule=self.schedule.clone(),
        )

    def to_dict(self):
        return {
            "interval": self.interval,
            "activity_type": self.activity_type,
            "start_minimized": self.start_minimized,
            "notifications_enabled": self.notifications_enabled,
            "profile_name": self.profile_name,
            "first_run_completed": self.first_run_completed,
            "prevent_sleep": self.prevent_sleep,
            "keep_display_on": self.keep_display_on,
            "idle_aware": self.idle_aware,
            "idle_threshold": self.idle_threshold,
            "zen_jiggle": self.zen_jiggle,
            "override_state": self.override_state,
            "override_until": self.override_until.isoformat() if self.override_until else None,
            "lifetime_activity_count": self.lifetime_activity_count,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "schedule": self.schedule.to_dict(),
        }


def apply_preset(config, preset_name):
    preset = PRESET_CONFIGS.get(preset_name)
    if not preset:
        config.profile_name = "Custom"
        return config

    config.interval = preset["interval"]
    config.activity_type = preset["activity_type"]
    config.schedule = preset["schedule"].clone()
    config.profile_name = preset_name
    return config


def config_from_raw(raw_config):
    activity_type = raw_config.get("activity_type", "F15 Key (Recommended)")
    if activity_type not in VALID_ACTIVITY_TYPES:
        activity_type = VALID_ACTIVITY_TYPES[0]

    profile_name = raw_config.get("profile_name", "Custom")
    if profile_name not in PRESET_CONFIGS:
        profile_name = "Custom"

    override_state = raw_config.get("override_state")
    if override_state not in VALID_OVERRIDE_STATES:
        override_state = None
    override_until = parse_datetime(raw_config.get("override_until"))
    if override_state is None or override_until is None:
        override_state = None
        override_until = None

    schedule = ScheduleConfig.from_raw(raw_config.get("schedule", {}))
    return AppConfig(
        interval=clamp_interval(raw_config.get("interval", 60)),
        activity_type=activity_type,
        start_minimized=bool(raw_config.get("start_minimized", True)),
        notifications_enabled=bool(raw_config.get("notifications_enabled", True)),
        profile_name=profile_name,
        first_run_completed=bool(raw_config.get("first_run_completed", False)),
        prevent_sleep=bool(raw_config.get("prevent_sleep", True)),
        keep_display_on=bool(raw_config.get("keep_display_on", False)),
        idle_aware=bool(raw_config.get("idle_aware", True)),
        idle_threshold=clamp_idle_threshold(raw_config.get("idle_threshold", 45)),
        zen_jiggle=bool(raw_config.get("zen_jiggle", True)),
        override_state=override_state,
        override_until=override_until,
        lifetime_activity_count=max(0, int(raw_config.get("lifetime_activity_count", 0) or 0)),
        last_activity_at=parse_datetime(raw_config.get("last_activity_at")),
        schedule=schedule,
    )


def quarantine_config(source_file, logger):
    """Move an unreadable config aside so the user can inspect what was lost."""
    try:
        backup = source_file.with_suffix(source_file.suffix + ".bad")
        if backup.exists():
            backup.unlink()
        source_file.rename(backup)
        logger.warning("Config at %s was unreadable; moved it to %s", source_file, backup)
    except OSError:
        logger.exception("Could not quarantine unreadable config at %s", source_file)


def load_app_config(logger):
    source_file = None
    raw_config = {}

    if CONFIG_FILE.exists():
        source_file = CONFIG_FILE
    elif LEGACY_CONFIG_FILE.exists():
        source_file = LEGACY_CONFIG_FILE

    if source_file:
        try:
            with open(source_file, "r", encoding="utf-8") as handle:
                raw_config = json.load(handle)
            if not isinstance(raw_config, dict):
                raise ValueError("Config root must be a JSON object")
            logger.info("Loaded configuration from %s", source_file)
        except Exception:
            logger.exception("Could not load config from %s; using defaults", source_file)
            quarantine_config(source_file, logger)
            raw_config = {}

    config = config_from_raw(raw_config)
    if source_file == LEGACY_CONFIG_FILE:
        logger.info("Migrating legacy config into %s", CONFIG_FILE)
        save_app_config(config, logger)
    return config


def save_app_config(config, logger):
    ensure_app_directories()
    write_json_atomic(CONFIG_FILE, config.to_dict())
    logger.debug("Saved configuration to %s", CONFIG_FILE)