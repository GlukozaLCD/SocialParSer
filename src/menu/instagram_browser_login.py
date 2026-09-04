"""Вход в Instagram через настоящий видимый браузер (Playwright), а не через
API-имитацию мобильного клиента (instagrapi).

Instagram отличает атипичный трафик мобильного API от обычного веб-браузера —
несколько попыток входа через instagrapi.Client.login() подряд упирались в
checkpoint типа "native_flow", который сам instagrapi (см. exceptions.py)
прямо документирует как непроходимый через API/ссылку, только через
официальное приложение. Реальный браузер, где пользователь сам вводит
логин/пароль и проходит любую проверку, выглядит для Instagram как обычный
человек — это то же самое, что открыть Instagram на телефоне.

Используется тот же Chromium, что и для TikTok (TikTokApi/Playwright), но в
видимом (headed) режиме — здесь это не автоматизация, а инструмент для
ручного входа человеком.
"""

from __future__ import annotations

import os
import time

from src.config_store import PROJECT_ROOT, SESSIONS_DIR

# Та же переменная и та же папка, что в src/adapters/tiktok.py — единое место
# установки/запуска браузера для портативности проекта.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(PROJECT_ROOT / ".playwright-browsers"))

from playwright.sync_api import sync_playwright  # noqa: E402 (после переменной окружения выше)

LOGIN_URL = "https://www.instagram.com/accounts/login/"
# Постоянный профиль браузера (не одноразовый контекст) — копит куки и
# localStorage между попытками входа, как обычный человеческий браузер,
# а не "чистое" окно, тут же логинящееся в Instagram.
BROWSER_PROFILE_DIR = SESSIONS_DIR / "instagram_browser_profile"
POLL_INTERVAL_SECONDS = 2
TIMEOUT_SECONDS = 600  # 10 минут на весь вход, включая возможную проверку


class BrowserLoginCancelled(Exception):
    """Пользователь нажал Ctrl+C во время ожидания входа."""


class BrowserLoginTimedOut(Exception):
    """Вход не был завершён за отведённое время."""


class BrowserLoginAborted(Exception):
    """Окно браузера закрылось иначе, не через успешный вход (например,
    пользователь сам закрыл его руками)."""


def get_sessionid_via_browser() -> str:
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(
        "Открываю окно браузера — войдите в Instagram-аккаунт для скрапинга "
        "вручную (логин, пароль, любая проверка, которую попросит Instagram). "
        "Программа сама увидит завершение входа, после этого окно можно закрыть.\n"
        f"На это отведено {TIMEOUT_SECONDS // 60} минут."
    )
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(BROWSER_PROFILE_DIR), headless=False
        )
        try:
            page = context.new_page()
            page.goto(LOGIN_URL)
            deadline = time.monotonic() + TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                sessionid = _find_sessionid(context)
                if sessionid:
                    return sessionid
                time.sleep(POLL_INTERVAL_SECONDS)
            raise BrowserLoginTimedOut(
                f"Не удалось дождаться входа за {TIMEOUT_SECONDS // 60} минут."
            )
        except KeyboardInterrupt:
            raise BrowserLoginCancelled from None
        except BrowserLoginTimedOut:
            raise
        except Exception as exc:
            raise BrowserLoginAborted(str(exc)) from exc
        finally:
            try:
                context.close()
            except Exception:
                pass


def _find_sessionid(context) -> str | None:
    for cookie in context.cookies():
        if cookie.get("name") == "sessionid" and "instagram.com" in cookie.get("domain", ""):
            return cookie["value"]
    return None
