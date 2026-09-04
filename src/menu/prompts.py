"""Общие для мастера и меню настроек вопросы (questionary).

Вынесено отдельно, чтобы setup_wizard.py и settings_menu.py не дублировали
одни и те же вопросы про выбор платформ / ввод учётных данных / добавление
паблика.
"""

from __future__ import annotations

import questionary
from instagrapi import Client as InstagramClient
from telethon.sync import TelegramClient

from src.config_store import SESSIONS_DIR, WatchlistSource
from src.menu.instagram_browser_login import (
    BrowserLoginAborted,
    BrowserLoginCancelled,
    BrowserLoginTimedOut,
    get_sessionid_via_browser,
)
from src.platforms import PLATFORMS, credential_fields, id_hint, platform_label


class Cancelled(Exception):
    """Пользователь прервал ввод (Ctrl+C / Esc) — сигнал «остановить всё»."""


class PlatformSetupFailed(Exception):
    """Не удалось установить сессию для конкретной платформы (например,
    Instagram запросил ручное подтверждение через приложение). В отличие от
    Cancelled — это не отказ пользователя от настройки вообще, а повод
    пропустить именно эту платформу и продолжить с остальными."""


def _unwrap(value):
    if value is None:
        raise Cancelled
    return value


def prompt_platforms_checkbox(preselected: list[str] | None = None) -> list[str]:
    preselected = preselected or []
    choices = [
        questionary.Choice(title=label["label"], value=key, checked=key in preselected)
        for key, label in PLATFORMS.items()
    ]
    return _unwrap(questionary.checkbox("Какие платформы подключить?", choices=choices).ask())


def prompt_credentials_for_platform(platform: str, existing: dict | None = None) -> dict:
    existing = existing or {}
    print(f"\n--- {platform_label(platform)} ---")

    # У Instagram набор обязательных полей зависит от выбранного режима —
    # общий цикл по credential_fields этого не умеет (спросил бы разом и
    # Graph API токен, и логин/пароль для скрапинга, даже когда нужно только
    # что-то одно).
    if platform == "instagram":
        return _collect_instagram_credentials(existing)

    result = {}
    for field in credential_fields(platform):
        asker = questionary.password if field.secret else questionary.text
        default = existing.get(field.name, "")
        value = _unwrap(asker(f"{field.label}:", default=default).ask())
        result[field.name] = value

    if platform == "telegram":
        _establish_telegram_session(result)

    return result


def _collect_instagram_credentials(existing: dict) -> dict:
    mode = _unwrap(
        questionary.select(
            "Режим Instagram:",
            choices=[
                questionary.Choice("Свои Business/Creator страницы (Graph API)", value="graph_api"),
                questionary.Choice("Чужие публичные страницы (вход в отдельный аккаунт)", value="scrape"),
            ],
            default=existing.get("mode"),
        ).ask()
    )

    if mode == "graph_api":
        token = _unwrap(
            questionary.password(
                "Graph API токен:", default=existing.get("graph_api_token", "")
            ).ask()
        )
        return {"mode": mode, "graph_api_token": token}

    username = _unwrap(
        questionary.text(
            "Логин отдельного аккаунта для скрапинга (для справки — входить будете прямо в браузере):",
            default=existing.get("session_username", ""),
        ).ask()
    )
    _establish_instagram_session_via_browser()
    # Пароль нигде не собирается и не хранится — вводится только один раз,
    # прямо в открывшемся браузере (см. _establish_instagram_session_via_browser).
    return {"mode": mode, "session_username": username}


def _establish_instagram_session_via_browser() -> None:
    # Вместо client.login(username, password) (прямая имитация мобильного
    # API) открываем настоящий видимый браузер и даём пользователю войти
    # самому — включая любую проверку, которую покажет Instagram. Причина:
    # мобильный API-трафик несколько раз подряд упирался в checkpoint типа
    # "native_flow", который сам instagrapi документирует как непроходимый
    # через код/ссылку (только через официальное приложение) — настоящий
    # браузер для Instagram неотличим от обычного человека.
    try:
        sessionid = get_sessionid_via_browser()
    except BrowserLoginCancelled:
        raise Cancelled
    except (BrowserLoginTimedOut, BrowserLoginAborted) as exc:
        print(
            f"Не удалось войти в Instagram через браузер ({exc}). "
            "Попробуйте ещё раз через python main.py settings."
        )
        raise PlatformSetupFailed("instagram") from exc

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_path = SESSIONS_DIR / "instagram.json"
    client = InstagramClient()
    try:
        client.login_by_sessionid(sessionid)
    except Exception as exc:
        print(f"Не удалось применить сессию из браузера ({exc}). Попробуйте войти ещё раз.")
        raise PlatformSetupFailed("instagram") from exc
    client.dump_settings(session_path)
    print("Готово — сессия Instagram сохранена, пароль нигде не сохраняется.")


def _establish_telegram_session(credentials: dict) -> None:
    # api_id/api_hash одних недостаточно для чтения каналов — нужна ещё
    # сессия Telethon. client.start() спросит телефон/код только если
    # сессии ещё нет или она недействительна; если уже есть рабочая —
    # ничего не спросит и просто подключится.
    while True:
        try:
            api_id = int(credentials["api_id"])
            break
        except ValueError:
            print("API ID должен быть числом.")
            credentials["api_id"] = _unwrap(questionary.text("API ID (my.telegram.org):").ask())

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_path = str(SESSIONS_DIR / "telegram.session")
    print("Подключаемся к Telegram — если сессии ещё нет, потребуется код из приложения.")
    try:
        with TelegramClient(session_path, api_id, credentials["api_hash"]) as client:
            client.start()
    except Cancelled:
        raise
    except Exception as exc:
        # Неверный код, флуд-контроль, неверные api_id/api_hash и т.п. — та же
        # логика, что и у Instagram: пропускаем платформу, не обнуляем всё.
        print(f"Не удалось войти в Telegram ({exc}). Проверьте api_id/api_hash и код, попробуйте позже.")
        raise PlatformSetupFailed("telegram") from exc


def prompt_new_source(available_platforms: list[str]) -> WatchlistSource:
    choices = [
        questionary.Choice(title=platform_label(p), value=p) for p in available_platforms
    ]
    platform = _unwrap(questionary.select("Платформа паблика:", choices=choices).ask())
    page_id = _unwrap(
        questionary.text(f"ID/handle паблика ({id_hint(platform)}):").ask()
    )
    display_name = _unwrap(questionary.text("Отображаемое имя:").ask())
    return WatchlistSource(platform=platform, id=page_id, display_name=display_name)
