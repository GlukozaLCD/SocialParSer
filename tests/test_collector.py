import unittest
from datetime import datetime, timezone

from src.adapters.base import PostLink
from src.collector import group_posts_by_public
from src.config_store import WatchlistSource


def _post(platform, public_id, url, when, post_id=None):
    return PostLink(
        platform=platform,
        public_id=public_id,
        public_name="ignored-here",
        post_url=url,
        published_at=when,
        post_id=post_id or url,
    )


class TestGroupPostsByPublic(unittest.TestCase):
    def test_groups_and_sorts_newest_first(self):
        sources = [
            WatchlistSource(platform="vk", id="pub1", display_name="Public One"),
            WatchlistSource(platform="telegram", id="pub2", display_name="Public Two"),
        ]
        posts = [
            _post("vk", "pub1", "old", datetime(2024, 1, 1, tzinfo=timezone.utc), post_id="111"),
            _post("vk", "pub1", "new", datetime(2024, 1, 3, tzinfo=timezone.utc), post_id="222"),
            _post("telegram", "pub2", "tg-post", datetime(2024, 1, 2, tzinfo=timezone.utc)),
        ]

        groups = group_posts_by_public(posts, sources)

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["platform"], "vk")
        self.assertEqual(groups[0]["public_name"], "Public One")
        self.assertEqual([p["post_url"] for p in groups[0]["posts"]], ["new", "old"])
        self.assertEqual([p["post_id"] for p in groups[0]["posts"]], ["222", "111"])
        self.assertEqual(groups[1]["platform"], "telegram")
        self.assertEqual([p["post_url"] for p in groups[1]["posts"]], ["tg-post"])

    def test_source_with_no_posts_still_appears_with_empty_list(self):
        sources = [WatchlistSource(platform="vk", id="empty-pub", display_name="Empty")]

        groups = group_posts_by_public([], sources)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["posts"], [])

    def test_no_sources_gives_empty_result(self):
        self.assertEqual(group_posts_by_public([], []), [])


if __name__ == "__main__":
    unittest.main()
