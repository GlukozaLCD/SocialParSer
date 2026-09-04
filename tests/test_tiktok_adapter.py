import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.adapters.tiktok import TikTokAdapter, _stats_to_post_metrics, _video_to_post_link
from src.config_store import WatchlistSource


class TestVideoToPostLink(unittest.TestCase):
    def test_builds_post_from_video_as_dict(self):
        source = WatchlistSource(platform="tiktok", id="someuser", display_name="Some User")
        video_data = {"id": "7123456789012345678", "createTime": 1714557600}

        post = _video_to_post_link(video_data, source)

        self.assertEqual(
            post.post_url, "https://www.tiktok.com/@someuser/video/7123456789012345678"
        )
        self.assertEqual(post.published_at, datetime.fromtimestamp(1714557600, tz=timezone.utc))
        self.assertEqual(post.platform, "tiktok")
        self.assertEqual(post.post_id, "7123456789012345678")


class TestStatsToPostMetrics(unittest.TestCase):
    def test_maps_all_five_fields(self):
        stats = {"playCount": "1000", "diggCount": "50", "commentCount": "4", "shareCount": "6", "collectCount": "9"}

        metrics = _stats_to_post_metrics(stats)

        self.assertEqual(
            (metrics.views, metrics.likes, metrics.comments, metrics.reposts, metrics.saves),
            (1000, 50, 4, 6, 9),
        )


def _mock_tiktok_api(user_info_payload: dict) -> MagicMock:
    mock_api = MagicMock()
    mock_api.__aenter__ = AsyncMock(return_value=mock_api)
    mock_api.__aexit__ = AsyncMock(return_value=False)
    mock_api.create_sessions = AsyncMock()
    mock_user = MagicMock()
    mock_user.info = AsyncMock(return_value=user_info_payload)
    mock_api.user.return_value = mock_user
    return mock_api


class TestFetchSubscriberCount(unittest.TestCase):
    @patch("src.adapters.tiktok.TikTokApi")
    def test_returns_follower_count_from_nested_userinfo(self, mock_api_cls):
        mock_api_cls.return_value = _mock_tiktok_api({"userInfo": {"stats": {"followerCount": 12345}}})

        adapter = TikTokAdapter(ms_token="token")
        source = WatchlistSource(platform="tiktok", id="someuser", display_name="Some User")

        self.assertEqual(adapter.fetch_subscriber_count(source), 12345)

    @patch("src.adapters.tiktok.TikTokApi")
    def test_falls_back_to_flat_stats_shape(self, mock_api_cls):
        mock_api_cls.return_value = _mock_tiktok_api({"stats": {"followerCount": "999"}})

        adapter = TikTokAdapter(ms_token="token")
        source = WatchlistSource(platform="tiktok", id="someuser", display_name="Some User")

        self.assertEqual(adapter.fetch_subscriber_count(source), 999)


if __name__ == "__main__":
    unittest.main()
