import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from alive_forever.core.scheduler import ScheduleConfig, TimeWindow, is_schedule_active, get_next_transition, format_transition
from alive_forever.core.config import AppConfig, apply_preset, config_from_raw

class TimezoneTests(unittest.TestCase):
    def schedule(self, start='09:00', end='17:00', days=None):
        return ScheduleConfig(enabled=True, timezone='Europe/London', windows=[TimeWindow(start,end, days or ['mon'])])

    def test_estonia_winter_and_summer(self):
        for month, day in [(1, 5), (7, 6)]:
            for hour, expected in [(10, False), (11, True), (18, True), (19, False)]:
                with self.subTest(month=month, hour=hour):
                    now=datetime(2026,month,day,hour,tzinfo=ZoneInfo('Europe/Tallinn'))
                    self.assertEqual(expected,is_schedule_active(self.schedule(),now))

    def test_overnight_uses_uk_day(self):
        now=datetime(2026,1,6,1,tzinfo=ZoneInfo('Europe/Tallinn'))
        self.assertTrue(is_schedule_active(self.schedule('22:00','06:00'),now))

    def test_dst_skipped_hour(self):
        s=self.schedule('01:30','03:00',['sun'])
        now=datetime(2026,3,29,0,59,tzinfo=timezone.utc)
        state, at=get_next_transition(s,now)
        self.assertEqual('active',state)
        self.assertEqual(datetime(2026,3,29,1,tzinfo=timezone.utc),at.astimezone(timezone.utc))
        self.assertIn('BST',format_transition((state,at)))

    def test_dst_repeated_hour(self):
        s=self.schedule('01:30','02:30',['sun'])
        state, at=get_next_transition(s,datetime(2026,10,25,0,45,tzinfo=timezone.utc))
        self.assertEqual('scheduled_off',state)
        self.assertEqual(datetime(2026,10,25,1,tzinfo=timezone.utc),at.astimezone(timezone.utc))
        self.assertFalse(is_schedule_active(s,at))

    def test_roundtrip_clone_presets(self):
        config=AppConfig(schedule=self.schedule())
        config=config_from_raw(config.to_dict()).clone()
        apply_preset(config,'Workday')
        self.assertEqual('Europe/London',config.schedule.timezone)

    def test_legacy_and_invalid(self):
        self.assertEqual('local',ScheduleConfig.from_raw({}).timezone)
        with self.assertRaises(ValueError):
            ScheduleConfig(timezone='Not/AZone')

    def test_transition_uk_time(self):
        state, at=get_next_transition(self.schedule(),datetime(2026,7,6,7,tzinfo=timezone.utc))
        self.assertEqual(9,at.hour)
        self.assertEqual('BST',at.tzname())
