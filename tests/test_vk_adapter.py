import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.adapters.base import AdapterError
from src.adapters.vk import VkAdapter, _item_to_post_link, _item_to_post_metrics
from src.config_store import WatchlistSource


def _response(payload: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = payload
    return mock


class TestItemToPostLink(unittest.TestCase):
    def test_builds_url_and_date(self):
        source = WatchlistSource(platform="vk", id="somepublic", display_name="Some Public")
        item = {"owner_id": -123, "id": 456, "date": 1700000000}

        post = _item_to_post_link(item, source)

        self.assertEqual(post.post_url, "https://vk.com/wall-123_456")
        self.assertEqual(post.published_at, datetime.fromtimestamp(1700000000, tz=timezone.utc))
        self.assertEqual(post.post_id, "-123_456")
        self.assertEqual(post.platform, "vk")
        self.assertEqual(post.public_name, "Some Public")


class TestItemToPostMetrics(unittest.TestCase):
    def test_maps_counts_and_leaves_saves_null(self):
        item = {
            "views": {"count": 1200},
            "likes": {"count": 34},
            "comments": {"count": 5},
            "reposts": {"count": 2},
        }

        metrics = _item_to_post_metrics(item)

        self.assertEqual((metrics.views, metrics.likes, metrics.comments, metrics.reposts), (1200, 34, 5, 2))
        self.assertIsNone(metrics.saves)


class TestOwnerParams(unittest.TestCase):
    def test_domain_for_text_id(self):
        adapter = VkAdapter(access_token="x")
        self.assertEqual(adapter._owner_params("somepublic"), {"domain": "somepublic"})

    def test_owner_id_for_numeric_id(self):
        adapter = VkAdapter(access_token="x")
        self.assertEqual(adapter._owner_params("123"), {"owner_id": -123})
        self.assertEqual(adapter._owner_params("-123"), {"owner_id": -123})


class TestFetchRecentPosts(unittest.TestCase):
    @patch("src.adapters.vk.requests.get")
    def test_stops_at_since_boundary_without_extra_pages(self, mock_get):
        now = 1_700_100_000
        since = datetime.fromtimestamp(now - 3600, tz=timezone.utc)
        items = [
            {"owner_id": -1, "id": 3, "date": now},
            {"owner_id": -1, "id": 2, "date": now - 1800},
            {"owner_id": -1, "id": 1, "date": now - 7200},  # старше since — граница
        ]
        mock_get.return_value = _response({"response": {"items": items}})

        adapter = VkAdapter(access_token="x")
        source = WatchlistSource(platform="vk", id="somepublic", display_name="P")
        posts = adapter.fetch_recent_posts(source, since)

        self.assertEqual(len(posts), 2)
        mock_get.assert_called_once()

    @patch("src.adapters.vk.requests.get")
    def test_raises_on_api_error(self, mock_get):
        mock_get.return_value = _response({"error": {"error_msg": "Invalid access token"}})

        adapter = VkAdapter(access_token="bad")
        source = WatchlistSource(platform="vk", id="somepublic", display_name="P")
        with self.assertRaises(AdapterError):
            adapter.fetch_recent_posts(source, datetime.now(timezone.utc))


class TestFetchPostMetrics(unittest.TestCase):
    @patch("src.adapters.vk.requests.get")
    def test_returns_metrics_for_found_post(self, mock_get):
        mock_get.return_value = _response(
            {"response": [{"views": {"count": 10}, "likes": {"count": 2}, "comments": {"count": 1}, "reposts": {"count": 0}}]}
        )

        adapter = VkAdapter(access_token="x")
        metrics = adapter.fetch_post_metrics("somepublic", "-1_3")

        self.assertEqual(metrics.views, 10)
        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args.kwargs["params"]["posts"], "-1_3")

    @patch("src.adapters.vk.requests.get")
    def test_raises_when_post_not_found(self, mock_get):
        mock_get.return_value = _response({"response": []})

        adapter = VkAdapter(access_token="x")
        with self.assertRaises(AdapterError):
            adapter.fetch_post_metrics("somepublic", "-1_999")


class TestFetchSubscriberCount(unittest.TestCase):
    @patch("src.adapters.vk.requests.get")
    def test_returns_members_count(self, mock_get):
        mock_get.return_value = _response({"response": {"groups": [{"members_count": 15400}]}})

        adapter = VkAdapter(access_token="x")
        source = WatchlistSource(platform="vk", id="somepublic", display_name="P")
        count = adapter.fetch_subscriber_count(source)

        self.assertEqual(count, 15400)
        self.assertEqual(mock_get.call_args.kwargs["params"]["group_id"], "somepublic")

    @patch("src.adapters.vk.requests.get")
    def test_strips_leading_dash_for_numeric_id(self, mock_get):
        mock_get.return_value = _response({"response": {"groups": [{"members_count": 100}]}})

        adapter = VkAdapter(access_token="x")
        source = WatchlistSource(platform="vk", id="-123", display_name="P")
        adapter.fetch_subscriber_count(source)

        self.assertEqual(mock_get.call_args.kwargs["params"]["group_id"], "123")

    @patch("src.adapters.vk.requests.get")
    def test_raises_when_group_not_found(self, mock_get):
        mock_get.return_value = _response({"response": {"groups": []}})

        adapter = VkAdapter(access_token="x")
        source = WatchlistSource(platform="vk", id="missing", display_name="P")
        with self.assertRaises(AdapterError):
            adapter.fetch_subscriber_count(source)


if __name__ == "__main__":
    unittest.main()
