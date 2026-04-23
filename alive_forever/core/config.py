"""Application configuration loading, migration, and presets."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from alive_forever.core.scheduler import ScheduleConfig, TimeWindow
from alive_forever.system.windows import CONFIG_FILE, LEGACY_CONFIG_FILE, ensure_app_directories


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


def clamp_interval(value):
    try:
        interval = int(value)
    except (TypeError, ValueError):
        return 60
    return max(10, min(300, interval))


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

    schedule = ScheduleConfig.from_raw(raw_config.get("schedule", {}))
    return AppConfig(
        interval=clamp_interval(raw_config.get("interval", 60)),
        activity_type=activity_type,
        start_minimized=bool(raw_config.get("start_minimized", True)),
        notifications_enabled=bool(raw_config.get("notifications_enabled", True)),
        profile_name=profile_name,
        lifetime_activity_count=max(0, int(raw_config.get("lifetime_activity_count", 0) or 0)),
        last_activity_at=parse_datetime(raw_config.get("last_activity_at")),
        schedule=schedule,
    )


def load_app_config(logger):
    source_file = None
    raw_config = {}

    try:
        if CONFIG_FILE.exists():
            source_file = CONFIG_FILE
        elif LEGACY_CONFIG_FILE.exists():
            source_file = LEGACY_CONFIG_FILE

        if source_file:
            with open(source_file, "r", encoding="utf-8") as handle:
                raw_config = json.load(handle)
            logger.info("Loaded configuration from %s", source_file)
    except Exception:
        logger.exception("Could not load config; using defaults")
        raw_config = {}

    config = config_from_raw(raw_config)
    if source_file == LEGACY_CONFIG_FILE:
        logger.info("Migrating legacy config into %s", CONFIG_FILE)
        save_app_config(config, logger)
    return config


def save_app_config(config, logger):
    ensure_app_directories()
    with open(CONFIG_FILE, "w", encoding="utf-8") as handle:
        json.dump(config.to_dict(), handle, indent=2)
    logger.info("Saved configuration to %s", CONFIG_FILE)