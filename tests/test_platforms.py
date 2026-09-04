import unittest

from src.platforms import missing_credential_fields


class TestMissingCredentialFields(unittest.TestCase):
    def test_vk_reports_missing_token(self):
        self.assertEqual(missing_credential_fields("vk", {}), ["access_token"])
        self.assertEqual(missing_credential_fields("vk", {"access_token": "x"}), [])

    def test_instagram_graph_api_mode_ignores_scrape_fields(self):
        # Регресс-тест: раньше проверка требовала все поля Instagram разом
        # (обоих режимов), из-за чего правильно настроенный graph_api
        # никогда не считался готовым.
        stored = {"mode": "graph_api", "graph_api_token": "token"}
        self.assertEqual(missing_credential_fields("instagram", stored), [])

    def test_instagram_graph_api_mode_missing_token(self):
        self.assertEqual(missing_credential_fields("instagram", {"mode": "graph_api"}), ["graph_api_token"])

    def test_instagram_scrape_mode_ignores_graph_api_field(self):
        stored = {"mode": "scrape", "session_username": "u"}
        self.assertEqual(missing_credential_fields("instagram", stored), [])

    def test_instagram_scrape_mode_username_is_optional(self):
        # Пароль больше не хранится (вход через браузер), а username — чисто
        # справочное поле: реальная готовность проверяется отдельно, по
        # наличию файла сессии (config_store.session_exists), не здесь.
        stored = {"mode": "scrape"}
        self.assertEqual(missing_credential_fields("instagram", stored), [])

    def test_instagram_without_mode(self):
        self.assertEqual(missing_credential_fields("instagram", {}), ["mode"])


if __name__ == "__main__":
    unittest.main()
