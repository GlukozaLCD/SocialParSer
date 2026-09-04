import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.adapters.base import AdapterError
from src.adapters.instagram import (
    InstagramGraphApiAdapter,
    InstagramScrapeAdapter,
    _graph_item_to_post_link,
    _media_to_post_link,
)
from src.config_store import WatchlistSource


def _ok_response(payload: dict) -> MagicMock:
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = payload
    return mock


class TestGraphItemToPostLink(unittest.TestCase):
    def test_builds_post_from_graph_api_item(self):
        source = WatchlistSource(platform="instagram", id="17841400000000000", display_name="Own Page")
        item = {
            "id": "18000000000000000",
            "permalink": "https://www.instagram.com/p/ABC123/",
            "timestamp": "2024-05-01T10:00:00+0000",
        }

        post = _graph_item_to_post_link(item, source)

        self.assertEqual(post.post_url, "https://www.instagram.com/p/ABC123/")
        self.assertEqual(post.published_at, datetime(2024, 5, 1, 10, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(post.platform, "instagram")
        self.assertEqual(post.post_id, "18000000000000000")


class TestMediaToPostLink(unittest.TestCase):
    def test_builds_post_from_instagrapi_media(self):
        source = WatchlistSource(platform="instagram", id="someuser", display_name="Some User")
        media = SimpleNamespace(
            code="XYZ789", pk=987654321, taken_at=datetime(2024, 5, 1, 10, 0, 0, tzinfo=timezone.utc)
        )

        post = _media_to_post_link(media, source)

        self.assertEqual(post.post_url, "https://www.instagram.com/p/XYZ789/")
        self.assertEqual(post.published_at, media.taken_at)
        self.assertEqual(post.post_id, "987654321")

    def test_naive_datetime_is_treated_as_utc(self):
        source = WatchlistSource(platform="instagram", id="someuser", display_name="Some User")
        media = SimpleNamespace(code="XYZ789", pk=987654321, taken_at=datetime(2024, 5, 1, 10, 0, 0))

        post = _media_to_post_link(media, source)

        self.assertEqual(post.published_at.tzinfo, timezone.utc)


class TestGraphApiFetchPostMetrics(unittest.TestCase):
    @patch("src.adapters.instagram.requests.get")
    def test_combines_basic_and_insights(self, mock_get):
        basic = _ok_response({"like_count": 10, "comments_count": 2})
        insights = _ok_response(
            {
                "data": [
                    {"name": "views", "values": [{"value": 500}]},
                    {"name": "saved", "values": [{"value": 4}]},
                    {"name": "shares", "values": [{"value": 1}]},
                ]
            }
        )
        mock_get.side_effect = [basic, insights]

        adapter = InstagramGraphApiAdapter(access_token="token")
        metrics = adapter.fetch_post_metrics("17841400000000000", "18000000000000000")

        self.assertEqual((metrics.likes, metrics.comments), (10, 2))
        self.assertEqual((metrics.views, metrics.saves, metrics.reposts), (500, 4, 1))

    @patch("src.adapters.instagram.requests.get")
    def test_missing_insights_permission_still_returns_basic_fields(self, mock_get):
        basic = _ok_response({"like_count": 10, "comments_count": 2})
        insights_error = MagicMock(status_code=403, json=lambda: {"error": {"message": "no permission"}})
        mock_get.side_effect = [basic, insights_error]

        adapter = InstagramGraphApiAdapter(access_token="token")
        metrics = adapter.fetch_post_metrics("17841400000000000", "18000000000000000")

        self.assertEqual((metrics.likes, metrics.comments), (10, 2))
        self.assertIsNone(metrics.views)
        self.assertIsNone(metrics.saves)


class TestScrapeFetchPostMetrics(unittest.TestCase):
    def test_maps_media_info_fields(self):
        adapter = InstagramScrapeAdapter()
        fake_client = MagicMock()
        fake_client.media_info.return_value = SimpleNamespace(view_count=100, like_count=20, comment_count=3)
        adapter._client = fake_client  # обходим реальный логин

        metrics = adapter.fetch_post_metrics("someuser", "987654321")

        fake_client.media_info.assert_called_once_with(987654321)
        self.assertEqual((metrics.views, metrics.likes, metrics.comments), (100, 20, 3))
        self.assertIsNone(metrics.reposts)
        self.assertIsNone(metrics.saves)


class TestGraphApiFetchSubscriberCount(unittest.TestCase):
    @patch("src.adapters.instagram.requests.get")
    def test_returns_followers_count(self, mock_get):
        mock_get.return_value = _ok_response({"followers_count": 8800})

        adapter = InstagramGraphApiAdapter(access_token="token")
        source = WatchlistSource(platform="instagram", id="17841400000000000", display_name="Own Page")

        self.assertEqual(adapter.fetch_subscriber_count(source), 8800)


class TestScrapeFetchSubscriberCount(unittest.TestCase):
    def test_returns_follower_count_from_user_info(self):
        adapter = InstagramScrapeAdapter()
        fake_client = MagicMock()
        fake_client.user_id_from_username.return_value = 555
        fake_client.user_info.return_value = SimpleNamespace(follower_count=8800)
        adapter._client = fake_client

        source = WatchlistSource(platform="instagram", id="someuser", display_name="Some User")
        count = adapter.fetch_subscriber_count(source)

        fake_client.user_id_from_username.assert_called_once_with("someuser")
        fake_client.user_info.assert_called_once_with(555)
        self.assertEqual(count, 8800)


class TestScrapeLogin(unittest.TestCase):
    def test_raises_adapter_error_when_no_session_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.adapters.instagram.SESSIONS_DIR", Path(tmp)):
                adapter = InstagramScrapeAdapter()
                with self.assertRaises(AdapterError):
                    adapter._login()

    @patch("src.adapters.instagram.Client")
    def test_loads_existing_session_without_calling_login(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with tempfile.TemporaryDirectory() as tmp:
            session_path = Path(tmp) / "instagram.json"
            session_path.write_text("{}", encoding="utf-8")
            with patch("src.adapters.instagram.SESSIONS_DIR", Path(tmp)):
                adapter = InstagramScrapeAdapter()
                client = adapter._login()

        mock_client.load_settings.assert_called_once_with(session_path)
        mock_client.login.assert_not_called()
        mock_client.login_by_sessionid.assert_not_called()
        self.assertIs(client, mock_client)


if __name__ == "__main__":
    unittest.main()
