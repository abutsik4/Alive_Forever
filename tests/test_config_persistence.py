import json
import logging
import tempfile
import unittest
from pathlib import Path

from alive_forever.core import config as config_module
from alive_forever.core.config import AppConfig, config_from_raw, load_app_config, save_app_config
from alive_forever.system.windows import write_json_atomic


class _QuietLogger(logging.Logger):
    def __init__(self):
        super().__init__("test", logging.CRITICAL + 1)


class AtomicWriteTests(unittest.TestCase):
    def test_write_json_atomic_creates_readable_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "nested" / "config.json"

            write_json_atomic(target, {"interval": 42})

            self.assertEqual({"interval": 42}, json.loads(target.read_text(encoding="utf-8")))

    def test_write_json_atomic_leaves_no_temp_files_behind(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "config.json"

            write_json_atomic(target, {"a": 1})
            write_json_atomic(target, {"a": 2})

            self.assertEqual(["config.json"], sorted(p.name for p in Path(temp_dir).iterdir()))

    def test_write_json_atomic_keeps_old_content_when_payload_is_unserializable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "config.json"
            write_json_atomic(target, {"keep": "me"})

            with self.assertRaises(TypeError):
                write_json_atomic(target, {"bad": object()})

            self.assertEqual({"keep": "me"}, json.loads(target.read_text(encoding="utf-8")))
            self.assertEqual(["config.json"], sorted(p.name for p in Path(temp_dir).iterdir()))


class ConfigLoadTests(unittest.TestCase):
    def setUp(self):
        self.logger = _QuietLogger()
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.temp_dir = Path(self._temp.name)

        self._original_config_file = config_module.CONFIG_FILE
        self._original_legacy = config_module.LEGACY_CONFIG_FILE
        config_module.CONFIG_FILE = self.temp_dir / "config.json"
        config_module.LEGACY_CONFIG_FILE = self.temp_dir / "legacy.json"

    def tearDown(self):
        config_module.CONFIG_FILE = self._original_config_file
        config_module.LEGACY_CONFIG_FILE = self._original_legacy

    def test_round_trip_preserves_schedule_and_counters(self):
        original = config_from_raw(
            {
                "interval": 90,
                "activity_type": "Both",
                "lifetime_activity_count": 1234,
                "schedule": {
                    "enabled": True,
                    "windows": [{"start": "08:30", "end": "17:30", "days": ["mon", "fri"]}],
                },
            }
        )
        save_app_config(original, self.logger)

        reloaded = load_app_config(self.logger)

        self.assertEqual(90, reloaded.interval)
        self.assertEqual("Both", reloaded.activity_type)
        self.assertEqual(1234, reloaded.lifetime_activity_count)
        self.assertTrue(reloaded.schedule.enabled)
        self.assertEqual(1, len(reloaded.schedule.windows))
        self.assertEqual("08:30", reloaded.schedule.windows[0].start)
        self.assertEqual(["mon", "fri"], reloaded.schedule.windows[0].days)

    def test_corrupt_config_is_quarantined_rather_than_silently_reset(self):
        config_module.CONFIG_FILE.write_text('{"interval": 90, tru', encoding="utf-8")

        loaded = load_app_config(self.logger)

        self.assertEqual(60, loaded.interval)
        self.assertTrue(config_module.CONFIG_FILE.with_suffix(".json.bad").exists())
        self.assertFalse(config_module.CONFIG_FILE.exists())

    def test_truncated_empty_config_does_not_raise(self):
        config_module.CONFIG_FILE.write_text("", encoding="utf-8")

        loaded = load_app_config(self.logger)

        self.assertIsInstance(loaded, AppConfig)
        self.assertEqual(60, loaded.interval)

    def test_non_object_json_root_is_rejected(self):
        config_module.CONFIG_FILE.write_text("[1, 2, 3]", encoding="utf-8")

        loaded = load_app_config(self.logger)

        self.assertEqual(60, loaded.interval)
        self.assertTrue(config_module.CONFIG_FILE.with_suffix(".json.bad").exists())

    def test_legacy_config_is_migrated_to_the_appdata_path(self):
        config_module.LEGACY_CONFIG_FILE.write_text(json.dumps({"interval": 120}), encoding="utf-8")

        loaded = load_app_config(self.logger)

        self.assertEqual(120, loaded.interval)
        self.assertTrue(config_module.CONFIG_FILE.exists())


class ClampIntervalTests(unittest.TestCase):
    def test_clamps_to_supported_range(self):
        self.assertEqual(10, config_module.clamp_interval(1))
        self.assertEqual(300, config_module.clamp_interval(9999))
        self.assertEqual(60, config_module.clamp_interval("not a number"))
        self.assertEqual(60, config_module.clamp_interval(None))
        self.assertEqual(45, config_module.clamp_interval("45"))


if __name__ == "__main__":
    unittest.main()
