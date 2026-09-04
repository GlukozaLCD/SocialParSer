import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.adapters.base import PostLink, PostMetrics
from src.config_store import MissingCredentialsError, WatchlistSource
from src.metrics_collector import (
    LinksFileNotFound,
    PostRef,
    _load_post_refs_from_file,
    collect_metrics,
    post_link_to_ref,
)


def _fake_adapter(metrics=None, subscribers=None):
    adapter = MagicMock()
    adapter.fetch_post_metrics.return_value = metrics
    adapter.fetch_subscriber_count.return_value = subscribers
    return adapter


class TestPostLinkToRef(unittest.TestCase):
    def test_converts_relevant_fields_only(self):
        post = PostLink(
            platform="vk",
            public_id="pub",
            public_name="Pub",
            post_url="https://vk.com/wall-1_2",
            published_at=datetime.now(timezone.utc),
            post_id="-1_2",
        )

        ref = post_link_to_ref(post)

        self.assertEqual((ref.platform, ref.public_id, ref.post_id, ref.post_url), ("vk", "pub", "-1_2", post.post_url))


@patch("src.metrics_collector.write_metrics_result", return_value=Path("fake.json"))
class TestCollectMetrics(unittest.TestCase):
    def test_collects_metrics_and_subscribers(self, _mock_write):
        with patch("src.metrics_collector.get_adapter") as mock_get_adapter:
            adapter = _fake_adapter(
                metrics=PostMetrics(views=10, likes=2, comments=1, reposts=0, saves=None), subscribers=500
            )
            mock_get_adapter.return_value = adapter

            posts = [PostRef(platform="vk", public_id="pub", post_id="1_2", post_url="url")]
            sources = [WatchlistSource(platform="vk", id="pub", display_name="Pub")]

            result = collect_metrics(date(2026, 8, 27), posts=posts, sources=sources, credentials={})

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["post_metrics"][0]["views"], 10)
            self.assertEqual(result["subscriber_counts"][0]["subscribers"], 500)
            adapter.fetch_post_metrics.assert_called_once_with("pub", "1_2")

    def test_missing_credentials_skip_platform_without_retrying(self, _mock_write):
        with patch("src.metrics_collector.get_adapter") as mock_get_adapter:
            mock_get_adapter.side_effect = MissingCredentialsError("vk", ["access_token"])

            posts = [
                PostRef(platform="vk", public_id="pub", post_id="1", post_url="u1"),
                PostRef(platform="vk", public_id="pub", post_id="2", post_url="u2"),
            ]
            sources = [WatchlistSource(platform="vk", id="pub", display_name="Pub")]

            result = collect_metrics(date(2026, 8, 27), posts=posts, sources=sources, credentials={})

            self.assertEqual(result["status"], "partial")
            self.assertEqual(len(result["errors"]), 3)  # 2 поста + 1 паблик
            mock_get_adapter.assert_called_once()  # не пытается снова на каждый пост/паблик

    def test_one_failed_post_does_not_stop_others(self, _mock_write):
        with patch("src.metrics_collector.get_adapter") as mock_get_adapter:
            adapter = MagicMock()
            adapter.fetch_post_metrics.side_effect = [
                PostMetrics(views=1, likes=None, comments=None, reposts=None, saves=None),
                Exception("boom"),
            ]
            mock_get_adapter.return_value = adapter

            posts = [
                PostRef(platform="vk", public_id="pub", post_id="1", post_url="u1"),
                PostRef(platform="vk", public_id="pub", post_id="2", post_url="u2"),
            ]

            result = collect_metrics(date(2026, 8, 27), posts=posts, sources=[], credentials={})

            self.assertEqual(len(result["post_metrics"]), 1)
            self.assertEqual(len(result["errors"]), 1)
            self.assertEqual(result["status"], "partial")

    def test_skip_metrics_flag(self, _mock_write):
        with patch("src.metrics_collector.get_adapter") as mock_get_adapter:
            adapter = _fake_adapter(subscribers=10)
            mock_get_adapter.return_value = adapter
            posts = [PostRef(platform="vk", public_id="pub", post_id="1", post_url="u1")]
            sources = [WatchlistSource(platform="vk", id="pub", display_name="Pub")]

            result = collect_metrics(
                date(2026, 8, 27), posts=posts, sources=sources, credentials={}, skip_metrics=True
            )

            adapter.fetch_post_metrics.assert_not_called()
            self.assertEqual(result["post_metrics"], [])
            self.assertEqual(len(result["subscriber_counts"]), 1)

    def test_skip_subscribers_flag(self, _mock_write):
        with patch("src.metrics_collector.get_adapter") as mock_get_adapter:
            adapter = _fake_adapter(metrics=PostMetrics(views=1, likes=None, comments=None, reposts=None, saves=None))
            mock_get_adapter.return_value = adapter
            posts = [PostRef(platform="vk", public_id="pub", post_id="1", post_url="u1")]
            sources = [WatchlistSource(platform="vk", id="pub", display_name="Pub")]

            result = collect_metrics(
                date(2026, 8, 27), posts=posts, sources=sources, credentials={}, skip_subscribers=True
            )

            adapter.fetch_subscriber_count.assert_not_called()
            self.assertEqual(result["subscriber_counts"], [])


class TestLoadPostRefsFromFile(unittest.TestCase):
    def test_flattens_publics_into_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_path = Path(tmp) / "links_2026-08-27.json"
            fake_path.write_text(
                json.dumps(
                    {
                        "publics": [
                            {
                                "platform": "vk",
                                "public_id": "pub",
                                "public_name": "Pub",
                                "posts": [{"post_id": "-1_2", "post_url": "url1", "published_at": "..."}],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with patch("src.metrics_collector.links_output_path", return_value=fake_path):
                refs = _load_post_refs_from_file(date(2026, 8, 27))

            self.assertEqual(len(refs), 1)
            self.assertEqual((refs[0].platform, refs[0].public_id, refs[0].post_id), ("vk", "pub", "-1_2"))

    def test_raises_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_path = Path(tmp) / "links_2020-01-01.json"
            with patch("src.metrics_collector.links_output_path", return_value=missing_path):
                with self.assertRaises(LinksFileNotFound):
                    _load_post_refs_from_file(date(2020, 1, 1))


if __name__ == "__main__":
    unittest.main()
