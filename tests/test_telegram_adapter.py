import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.adapters.telegram import TelegramAdapter, _message_to_post_link, _message_to_post_metrics
from src.config_store import WatchlistSource


class TestMessageToPostLink(unittest.TestCase):
    def test_regular_message_becomes_post(self):
        source = WatchlistSource(platform="telegram", id="somechannel", display_name="Some Channel")
        message = SimpleNamespace(id=42, date=datetime(2024, 5, 1, tzinfo=timezone.utc), action=None)

        post = _message_to_post_link(message, source)

        self.assertIsNotNone(post)
        self.assertEqual(post.post_url, "https://t.me/somechannel/42")
        self.assertEqual(post.published_at, message.date)
        self.assertEqual(post.platform, "telegram")
        self.assertEqual(post.post_id, "42")

    def test_service_message_is_skipped(self):
        source = WatchlistSource(platform="telegram", id="somechannel", display_name="Some Channel")
        message = SimpleNamespace(id=1, date=datetime.now(timezone.utc), action=object())

        post = _message_to_post_link(message, source)

        self.assertIsNone(post)


class TestMessageToPostMetrics(unittest.TestCase):
    def test_views_and_forwards_without_reactions(self):
        message = SimpleNamespace(views=150, forwards=7, reactions=None)

        metrics = _message_to_post_metrics(message)

        self.assertEqual((metrics.views, metrics.reposts), (150, 7))
        self.assertIsNone(metrics.likes)
        self.assertIsNone(metrics.comments)
        self.assertIsNone(metrics.saves)

    def test_likes_are_sum_of_reactions(self):
        reaction_counts = [SimpleNamespace(count=3), SimpleNamespace(count=5)]
        message = SimpleNamespace(
            views=10, forwards=0, reactions=SimpleNamespace(results=reaction_counts)
        )

        metrics = _message_to_post_metrics(message)

        self.assertEqual(metrics.likes, 8)


class TestFetchSubscriberCount(unittest.TestCase):
    @patch("src.adapters.telegram.TelegramClient")
    def test_returns_participants_count(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.return_value = SimpleNamespace(full_chat=SimpleNamespace(participants_count=4200))
        mock_client_cls.return_value = mock_client

        adapter = TelegramAdapter(api_id="123", api_hash="hash", session_path=Path("dummy.session"))
        source = WatchlistSource(platform="telegram", id="somechannel", display_name="Some Channel")

        count = adapter.fetch_subscriber_count(source)

        self.assertEqual(count, 4200)


if __name__ == "__main__":
    unittest.main()
