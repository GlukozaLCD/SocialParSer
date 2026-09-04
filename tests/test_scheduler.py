import unittest
from datetime import datetime, time

from src.scheduler import parse_time_of_day, seconds_until


class TestParseTimeOfDay(unittest.TestCase):
    def test_parses_zero_padded(self):
        self.assertEqual(parse_time_of_day("09:00"), time(9, 0))

    def test_parses_single_digit_hour(self):
        self.assertEqual(parse_time_of_day("9:00"), time(9, 0))

    def test_rejects_out_of_range_hour(self):
        with self.assertRaises(ValueError):
            parse_time_of_day("25:00")

    def test_rejects_out_of_range_minute(self):
        with self.assertRaises(ValueError):
            parse_time_of_day("12:99")

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_time_of_day("abc")


class TestSecondsUntil(unittest.TestCase):
    def test_target_later_today(self):
        now = datetime(2026, 8, 27, 8, 0, 0)
        result = seconds_until(now, time(9, 0))
        self.assertEqual(result, 3600)

    def test_target_already_passed_today_waits_until_tomorrow(self):
        now = datetime(2026, 8, 27, 10, 0, 0)
        result = seconds_until(now, time(9, 0))
        self.assertEqual(result, 23 * 3600)

    def test_exact_match_counts_as_passed(self):
        now = datetime(2026, 8, 27, 9, 0, 0)
        result = seconds_until(now, time(9, 0))
        self.assertEqual(result, 24 * 3600)


if __name__ == "__main__":
    unittest.main()
