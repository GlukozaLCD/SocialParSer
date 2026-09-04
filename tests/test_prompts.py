import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.menu.instagram_browser_login import (
    BrowserLoginAborted,
    BrowserLoginCancelled,
    BrowserLoginTimedOut,
)
from src.menu.prompts import (
    Cancelled,
    PlatformSetupFailed,
    _establish_instagram_session_via_browser,
    _establish_telegram_session,
)


class TestEstablishInstagramSessionViaBrowser(unittest.TestCase):
    @patch("src.menu.prompts.InstagramClient")
    @patch("src.menu.prompts.get_sessionid_via_browser")
    def test_success_calls_login_by_sessionid_and_dumps_settings(self, mock_get_sessionid, mock_client_cls):
        mock_get_sessionid.return_value = "1234567890abcdefghijklmnopqrstuvwxyz"
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.menu.prompts.SESSIONS_DIR", Path(tmp)):
                _establish_instagram_session_via_browser()

        mock_client.login_by_sessionid.assert_called_once_with(mock_get_sessionid.return_value)
        mock_client.dump_settings.assert_called_once()

    @patch("src.menu.prompts.get_sessionid_via_browser")
    def test_ctrl_c_during_browser_wait_propagates_as_cancelled(self, mock_get_sessionid):
        mock_get_sessionid.side_effect = BrowserLoginCancelled()

        with self.assertRaises(Cancelled):
            _establish_instagram_session_via_browser()

    @patch("src.menu.prompts.get_sessionid_via_browser")
    def test_timeout_raises_platform_setup_failed_not_cancelled(self, mock_get_sessionid):
        # Регресс-тест на тот же класс бага, что раньше был с Instagram
        # checkpoint: неудача именно этой платформы не должна обнулять весь
        # мастер целиком (и уже введённые данные по другим платформам).
        mock_get_sessionid.side_effect = BrowserLoginTimedOut("не дождался входа")

        with self.assertRaises(PlatformSetupFailed):
            _establish_instagram_session_via_browser()

    @patch("src.menu.prompts.get_sessionid_via_browser")
    def test_browser_aborted_raises_platform_setup_failed(self, mock_get_sessionid):
        mock_get_sessionid.side_effect = BrowserLoginAborted("окно закрыто")

        with self.assertRaises(PlatformSetupFailed):
            _establish_instagram_session_via_browser()

    @patch("src.menu.prompts.InstagramClient")
    @patch("src.menu.prompts.get_sessionid_via_browser")
    def test_invalid_sessionid_raises_platform_setup_failed(self, mock_get_sessionid, mock_client_cls):
        mock_get_sessionid.return_value = "somesessionid"
        mock_client = MagicMock()
        mock_client.login_by_sessionid.side_effect = Exception("Invalid sessionid")
        mock_client_cls.return_value = mock_client

        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.menu.prompts.SESSIONS_DIR", Path(tmp)):
                with self.assertRaises(PlatformSetupFailed):
                    _establish_instagram_session_via_browser()


class TestEstablishTelegramSession(unittest.TestCase):
    @patch("src.menu.prompts.TelegramClient")
    def test_generic_login_failure_raises_platform_setup_failed(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.start.side_effect = Exception("boom")
        mock_client_cls.return_value = mock_client

        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.menu.prompts.SESSIONS_DIR", Path(tmp)):
                with self.assertRaises(PlatformSetupFailed):
                    _establish_telegram_session({"api_id": "123", "api_hash": "hash"})


if __name__ == "__main__":
    unittest.main()
