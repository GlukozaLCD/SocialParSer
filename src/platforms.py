"""Статический реестр поддерживаемых платформ.

Это не логика доступа к платформам (та появится в адаптерах Фазы 2),
а декларативные метаданные: что показывать в меню и какие поля
учётных данных обязательны для каждой платформы. Мастер и меню настроек
строят вопросы по этому реестру, чтобы список платформ не был продублирован
в нескольких местах программы.
"""

from __future__ import annotations

from typing import NamedTuple


class CredentialField(NamedTuple):
    name: str
    label: str
    secret: bool  # True -> вводить через маскированное поле (пароль/токен)


PLATFORMS: dict[str, dict] = {
    "vk": {
        "label": "VK",
        "credential_fields": [
            CredentialField("access_token", "Access-токен (право wall)", True),
        ],
        "id_hint": "короткое имя паблика (vk.com/имя) или числовой ID группы",
    },
    "telegram": {
        "label": "Telegram",
        "credential_fields": [
            CredentialField("api_id", "API ID (my.telegram.org)", False),
            CredentialField("api_hash", "API HASH (my.telegram.org)", True),
        ],
        "id_hint": "юзернейм публичного канала без @",
    },
    "youtube": {
        "label": "YouTube",
        "credential_fields": [
            CredentialField("api_key", "API key (YouTube Data API v3)", True),
        ],
        "id_hint": "ID канала (начинается с UC...) либо @handle",
    },
    "instagram": {
        "label": "Instagram",
        # "mode" различает свои Business/Creator страницы (Graph API) и чужие
        # публичные страницы (вход в отдельный аккаунт через instagrapi).
        # Список ниже — справочный для UI (мастер/меню показывают все возможные
        # поля с пояснением "для mode=..."); реальную, зависящую от режима
        # обязательность полей проверяет missing_credential_fields() ниже —
        # им пользуются и registry.py, и меню, и config_store.validate().
        # Пароля для mode=scrape тут нет: вход происходит через браузер
        # (см. src/menu/instagram_browser_login.py), пароль не собирается и
        # не сохраняется вообще.
        "credential_fields": [
            CredentialField("mode", "Режим: graph_api (свои страницы) или scrape (чужие)", False),
            CredentialField("graph_api_token", "Graph API токен (для mode=graph_api)", True),
            CredentialField("session_username", "Логин отдельного аккаунта, справочно (для mode=scrape)", False),
        ],
        "id_hint": "юзернейм страницы (mode=scrape) или ID бизнес-аккаунта (mode=graph_api)",
    },
    "tiktok": {
        "label": "TikTok",
        "credential_fields": [
            CredentialField(
                "ms_token",
                "ms_token — cookie сессии из DevTools браузера после входа на tiktok.com",
                True,
            ),
        ],
        "id_hint": "юзернейм профиля без @",
    },
}


def platform_label(platform: str) -> str:
    return PLATFORMS[platform]["label"]


def credential_fields(platform: str) -> list[CredentialField]:
    return PLATFORMS[platform]["credential_fields"]


def id_hint(platform: str) -> str:
    return PLATFORMS[platform]["id_hint"]


def missing_credential_fields(platform: str, stored: dict) -> list[str]:
    """Каких полей не хватает в уже сохранённых credentials этой платформы.

    Пустой список — платформа готова к использованию. Instagram — особый
    случай: обязательность полей зависит от выбранного режима (`mode`), а не
    от полного списка credential_fields (тот содержит поля сразу обоих
    режимов). Единственное место, которое это знает — используется и
    реестром адаптеров, и меню настроек, и config_store.validate(), чтобы не
    разъезжаться в три разные проверки одного и того же.

    Для mode=scrape здесь больше не проверяется пароль (он не хранится) и
    даже не username (чисто справочное поле) — реальная готовность зависит от
    того, есть ли уже сохранённая браузером сессия на диске, а это проверяет
    отдельно settings_menu._is_connected() через config_store.session_exists():
    заводить сюда, в platforms.py, зависимость от файловой системы нельзя —
    config_store.py уже импортирует из platforms.py, обратная зависимость
    была бы циклическим импортом.
    """
    if platform == "instagram":
        mode = stored.get("mode")
        if mode == "graph_api":
            return [] if stored.get("graph_api_token") else ["graph_api_token"]
        if mode == "scrape":
            return []
        return ["mode"]
    return [f.name for f in credential_fields(platform) if not stored.get(f.name)]
