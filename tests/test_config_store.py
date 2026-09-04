import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import config_store
from src.config_store import WatchlistSource, has_session, reset_session, session_exists, validate


class TestValidate(unittest.TestCase):
    def test_empty_watchlist_has_no_problems(self):
        self.assertEqual(validate([], {}), [])

    def test_fully_configured_watchlist_has_no_problems(self):
        sources = [WatchlistSource(platform="vk", id="pub", display_name="Pub")]
        credentials = {"vk": {"access_token": "x"}}

        self.assertEqual(validate(sources, credentials), [])

    def test_reports_all_problems_not_just_first(self):
        sources = [
            WatchlistSource(platform="vk", id="pub1", display_name="Pub1"),
            WatchlistSource(platform="youtube", id="pub2", display_name="Pub2"),
        ]

        problems = validate(sources, {})

        self.assertEqual(len(problems), 2)
        platforms_with_problems = {p.platform for p in problems}
        self.assertEqual(platforms_with_problems, {"vk", "youtube"})

    def test_instagram_graph_api_mode_is_not_flagged_as_incomplete(self):
        sources = [WatchlistSource(platform="instagram", id="17841400000000000", display_name="Own Page")]
        credentials = {"instagram": {"mode": "graph_api", "graph_api_token": "token"}}

        self.assertEqual(validate(sources, credentials), [])


class TestSessionReset(unittest.TestCase):
    def test_has_session_true_for_telegram_and_instagram_only(self):
        self.assertTrue(has_session("telegram"))
        self.assertTrue(has_session("instagram"))
        self.assertFalse(has_session("vk"))
        self.assertFalse(has_session("youtube"))
        self.assertFalse(has_session("tiktok"))

    def test_reset_session_deletes_existing_file_and_reports_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            session_file = sessions_dir / "instagram.json"
            session_file.write_text("{}", encoding="utf-8")

            with patch.object(config_store, "SESSIONS_DIR", sessions_dir):
                result = reset_session("instagram")

            self.assertTrue(result)
            self.assertFalse(session_file.exists())

    def test_reset_session_returns_false_when_nothing_to_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(config_store, "SESSIONS_DIR", Path(tmp)):
                self.assertFalse(reset_session("instagram"))

    def test_reset_session_returns_false_for_platform_without_sessions(self):
        self.assertFalse(reset_session("vk"))

    def test_reset_session_also_removes_instagram_browser_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            session_file = sessions_dir / "instagram.json"
            session_file.write_text("{}", encoding="utf-8")
            profile_dir = sessions_dir / "instagram_browser_profile"
            profile_dir.mkdir()
            (profile_dir / "Default").mkdir()
            (profile_dir / "Default" / "Cookies").write_text("data", encoding="utf-8")

            with patch.object(config_store, "SESSIONS_DIR", sessions_dir):
                result = reset_session("instagram")

            self.assertTrue(result)
            self.assertFalse(session_file.exists())
            self.assertFalse(profile_dir.exists())


class TestSessionExists(unittest.TestCase):
    def test_true_when_session_file_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            (sessions_dir / "instagram.json").write_text("{}", encoding="utf-8")

            with patch.object(config_store, "SESSIONS_DIR", sessions_dir):
                self.assertTrue(session_exists("instagram"))

    def test_false_when_session_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(config_store, "SESSIONS_DIR", Path(tmp)):
                self.assertFalse(session_exists("instagram"))

    def test_false_for_platform_without_sessions(self):
        self.assertFalse(session_exists("vk"))


if __name__ == "__main__":
    unittest.main()
