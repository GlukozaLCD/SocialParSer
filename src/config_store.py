"""Загрузка/сохранение конфигурации: список пабликов и учётные данные платформ.

Пользователь не редактирует эти файлы напрямую — только через мастер первого
запуска и меню настроек (src/menu). Здесь — единственное место, которое знает
формат config/watchlist.json и config/credentials.json.

Все пути считаются от корня проекта (PROJECT_ROOT), а не от текущей рабочей
директории и не от системных папок пользователя (APPDATA, ~/.config) — это
то, что позволяет скопировать папку проекта на другую машину и получить
рабочую программу без правки путей.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from src.platforms import PLATFORMS, missing_credential_fields

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
WATCHLIST_PATH = CONFIG_DIR / "watchlist.json"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"
# Файлы сессий (например, Telethon для Telegram) — внутри проекта, а не в
# системных директориях пользователя, иначе портативность папки сломается.
SESSIONS_DIR = CONFIG_DIR / "sessions"

# Не у всех платформ есть отдельный файл сессии: VK/YouTube/TikTok обходятся
# одним токеном без сохранённого состояния, а Telegram/Instagram — нет
# (Telethon и instagrapi имитируют отдельное "устройство", которое должно
# оставаться одним и тем же между запусками/попытками входа).
SESSION_FILENAMES = {
    "telegram": "telegram.session",
    "instagram": "instagram.json",
}

CREDENTIALS_WARNING = (
    "Этот файл содержит личные токены и данные сессий для ваших аккаунтов. "
    "Храните его при себе и будьте осторожны, если пересылаете папку проекта "
    "другим людям — вместе с ней уедут и эти секреты."
)


@dataclass
class WatchlistSource:
    platform: str
    id: str
    display_name: str


class MissingCredentialsError(Exception):
    def __init__(self, platform: str, missing_fields: list[str]):
        self.platform = platform
        self.missing_fields = missing_fields
        fields = ", ".join(missing_fields)
        super().__init__(
            f"Для платформы «{PLATFORMS[platform]['label']}» не заданы поля: {fields}. "
            f"Зайдите в python main.py settings -> Учётные данные, чтобы их добавить."
        )


def is_configured() -> bool:
    """Есть ли уже сохранённая конфигурация (пройден ли мастер первого запуска)."""
    return CREDENTIALS_PATH.exists()


def load_watchlist() -> list[WatchlistSource]:
    if not WATCHLIST_PATH.exists():
        return []
    raw = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    return [WatchlistSource(**item) for item in raw.get("sources", [])]


def save_watchlist(sources: list[WatchlistSource]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"sources": [asdict(s) for s in sources]}
    WATCHLIST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_credentials() -> dict[str, dict]:
    if not CREDENTIALS_PATH.exists():
        return {}
    raw = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    raw.pop("_warning", None)
    return raw


def save_credentials(credentials: dict[str, dict]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # "_warning" пишется прямо в файл, чтобы предупреждение было видно и при
    # прямом открытии credentials.json в редакторе, а не только в консоли
    # в момент сохранения.
    payload = {"_warning": CREDENTIALS_WARNING, **credentials}
    CREDENTIALS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def has_session(platform: str) -> bool:
    return platform in SESSION_FILENAMES


def session_exists(platform: str) -> bool:
    """В отличие от has_session (платформа в принципе умеет иметь сессию),
    отвечает — реально ли сейчас на диске лежит файл сессии этой платформы.
    Для Instagram (mode=scrape) это единственный надёжный признак того, что
    браузерный вход (см. src/menu/instagram_browser_login.py) был пройден
    хотя бы раз — credentials.json к этому моменту может уже не отражать
    реальность, если сессию потом сбросили через reset_session()."""
    filename = SESSION_FILENAMES.get(platform)
    return bool(filename) and (SESSIONS_DIR / filename).exists()


def reset_session(platform: str) -> bool:
    """Удаляет сохранённую сессию/"устройство" для платформы (если она есть).

    Нужно, когда сама сессия — а не токен/пароль — стала причиной проблем:
    например, Instagram привязал отпечаток устройства к заблокированной
    попытке входа, и повторное использование того же отпечатка не помогает
    (см. .plans-историю про checkpoint). Сброс заставляет создать новое
    "устройство" при следующем входе. Пароль/токен из credentials.json при
    этом не трогается — их пользователь вводит отдельно.

    Возвращает True, если файл сессии или профиль браузера реально
    существовали и были удалены.
    """
    filename = SESSION_FILENAMES.get(platform)
    if not filename:
        return False
    removed = False
    path = SESSIONS_DIR / filename
    if path.exists():
        path.unlink()
        removed = True
    if platform == "instagram":
        # Постоянный профиль браузера (куки/localStorage) — тоже часть
        # "отпечатка", который должен сбрасываться вместе с instagram.json.
        browser_profile_dir = SESSIONS_DIR / "instagram_browser_profile"
        if browser_profile_dir.exists():
            shutil.rmtree(browser_profile_dir)
            removed = True
    return removed


def validate(sources: list[WatchlistSource], credentials: dict[str, dict]) -> list[MissingCredentialsError]:
    """Проверка готовности к запуску: какие платформы из watchlist не до конца
    настроены. Пустой список — можно запускать run-once. Возвращает все
    проблемы разом (не останавливается на первой) — используется меню
    настроек как раз затем, чтобы показать пользователю полную картину, а не
    заставлять чинить по одной ошибке за раз."""
    used_platforms = {s.platform for s in sources}
    problems = []
    for platform in sorted(used_platforms):
        stored = credentials.get(platform, {})
        missing = missing_credential_fields(platform, stored)
        if missing:
            problems.append(MissingCredentialsError(platform, missing))
    return problems
