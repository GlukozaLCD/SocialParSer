import unittest
from unittest.mock import MagicMock

from src.menu.instagram_browser_login import _find_sessionid


class TestFindSessionId(unittest.TestCase):
    def test_returns_value_when_instagram_sessionid_cookie_present(self):
        context = MagicMock()
        context.cookies.return_value = [
            {"name": "csrftoken", "value": "abc", "domain": ".instagram.com"},
            {"name": "sessionid", "value": "123456789abcdef", "domain": ".instagram.com"},
        ]

        self.assertEqual(_find_sessionid(context), "123456789abcdef")

    def test_returns_none_when_no_sessionid_cookie(self):
        context = MagicMock()
        context.cookies.return_value = [{"name": "csrftoken", "value": "abc", "domain": ".instagram.com"}]

        self.assertIsNone(_find_sessionid(context))

    def test_ignores_sessionid_cookie_from_other_domain(self):
        context = MagicMock()
        context.cookies.return_value = [{"name": "sessionid", "value": "xyz", "domain": ".otherdomain.com"}]

        self.assertIsNone(_find_sessionid(context))


if __name__ == "__main__":
    unittest.main()
