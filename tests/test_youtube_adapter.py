import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.adapters.base import AdapterError
from src.adapters.youtube import YoutubeAdapter, _item_to_post_link
from src.config_store import WatchlistSource


def _ok_response(payload: dict) -> MagicMock:
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = payload
    return mock


class TestItemToPostLink(unittest.TestCase):
    def test_builds_url_and_utc_date(self):
        source = WatchlistSource(platform="youtube", id="UCxxx", display_name="Chan")
        item = {
            "snippet": {"publishedAt": "2024-05-01T10:00:00Z"},
            "contentDetails": {"videoId": "abc123"},
        }

        post = _item_to_post_link(item, source)

        self.assertEqual(post.post_url, "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(post.published_at, datetime(2024, 5, 1, 10, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(post.post_id, "abc123")


class TestFetchRecentPosts(unittest.TestCase):
    @patch("src.adapters.youtube.requests.get")
    def test_resolves_uploads_playlist_and_filters_by_date(self, mock_get):
        channels_payload = _ok_response(
            {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUxxx"}}}]}
        )
        playlist_payload = _ok_response(
            {
                "items": [
                    {
                        "snippet": {"publishedAt": "2024-05-01T12:00:00Z"},
                        "contentDetails": {"videoId": "new"},
                    },
                    {
                        "snippet": {"publishedAt": "2024-04-01T12:00:00Z"},
                        "contentDetails": {"videoId": "old"},
                    },
                ]
            }
        )
        mock_get.side_effect = [channels_payload, playlist_payload]

        adapter = YoutubeAdapter(api_key="key")
        source = WatchlistSource(platform="youtube", id="UCxxx", display_name="Chan")
        since = datetime(2024, 4, 15, tzinfo=timezone.utc)

        posts = adapter.fetch_recent_posts(source, since)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].post_url, "https://www.youtube.com/watch?v=new")

    @patch("src.adapters.youtube.requests.get")
    def test_raises_when_channel_not_found(self, mock_get):
        mock_get.return_value = _ok_response({"items": []})

        adapter = YoutubeAdapter(api_key="key")
        source = WatchlistSource(platform="youtube", id="UCmissing", display_name="Chan")
        with self.assertRaises(AdapterError):
            adapter.fetch_recent_posts(source, datetime.now(timezone.utc))


class TestFetchPostMetrics(unittest.TestCase):
    @patch("src.adapters.youtube.requests.get")
    def test_returns_metrics_converted_to_int(self, mock_get):
        mock_get.return_value = _ok_response(
            {"items": [{"statistics": {"viewCount": "1500", "likeCount": "42", "commentCount": "3"}}]}
        )

        adapter = YoutubeAdapter(api_key="key")
        metrics = adapter.fetch_post_metrics("UCxxx", "abc123")

        self.assertEqual((metrics.views, metrics.likes, metrics.comments), (1500, 42, 3))
        self.assertIsNone(metrics.reposts)
        self.assertIsNone(metrics.saves)

    @patch("src.adapters.youtube.requests.get")
    def test_missing_like_count_is_none_not_error(self, mock_get):
        # автор мог скрыть счётчик лайков — поле просто отсутствует в ответе
        mock_get.return_value = _ok_response({"items": [{"statistics": {"viewCount": "10"}}]})

        adapter = YoutubeAdapter(api_key="key")
        metrics = adapter.fetch_post_metrics("UCxxx", "abc123")

        self.assertEqual(metrics.views, 10)
        self.assertIsNone(metrics.likes)

    @patch("src.adapters.youtube.requests.get")
    def test_raises_when_video_not_found(self, mock_get):
        mock_get.return_value = _ok_response({"items": []})

        adapter = YoutubeAdapter(api_key="key")
        with self.assertRaises(AdapterError):
            adapter.fetch_post_metrics("UCxxx", "missing")


class TestFetchSubscriberCount(unittest.TestCase):
    @patch("src.adapters.youtube.requests.get")
    def test_returns_subscriber_count(self, mock_get):
        mock_get.return_value = _ok_response(
            {"items": [{"statistics": {"subscriberCount": "15400", "hiddenSubscriberCount": False}}]}
        )

        adapter = YoutubeAdapter(api_key="key")
        source = WatchlistSource(platform="youtube", id="UCxxx", display_name="Chan")
        count = adapter.fetch_subscriber_count(source)

        self.assertEqual(count, 15400)

    @patch("src.adapters.youtube.requests.get")
    def test_hidden_subscriber_count_is_none(self, mock_get):
        mock_get.return_value = _ok_response({"items": [{"statistics": {"hiddenSubscriberCount": True}}]})

        adapter = YoutubeAdapter(api_key="key")
        source = WatchlistSource(platform="youtube", id="UCxxx", display_name="Chan")

        self.assertIsNone(adapter.fetch_subscriber_count(source))

    @patch("src.adapters.youtube.requests.get")
    def test_raises_when_channel_not_found(self, mock_get):
        mock_get.return_value = _ok_response({"items": []})

        adapter = YoutubeAdapter(api_key="key")
        source = WatchlistSource(platform="youtube", id="UCmissing", display_name="Chan")
        with self.assertRaises(AdapterError):
            adapter.fetch_subscriber_count(source)


if __name__ == "__main__":
    unittest.main()
