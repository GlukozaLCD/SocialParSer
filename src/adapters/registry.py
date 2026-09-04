"""Фабрика адаптеров: platform + credentials -> готовый PlatformAdapter."""

from __future__ import annotations

from src.adapters.base import PlatformAdapter
from src.adapters.instagram import InstagramGraphApiAdapter, InstagramScrapeAdapter
from src.adapters.telegram import TelegramAdapter
from src.adapters.tiktok import TikTokAdapter
from src.adapters.vk import VkAdapter
from src.adapters.youtube import YoutubeAdapter
from src.config_store import SESSIONS_DIR, MissingCredentialsError
from src.platforms import missing_credential_fields


def get_adapter(platform: str, credentials: dict) -> PlatformAdapter:
    stored = credentials.get(platform, {})

    missing = missing_credential_fields(platform, stored)
    if missing:
        raise MissingCredentialsError(platform, missing)

    if platform == "vk":
        return VkAdapter(access_token=stored["access_token"])
    if platform == "youtube":
        return YoutubeAdapter(api_key=stored["api_key"])
    if platform == "tiktok":
        return TikTokAdapter(ms_token=stored["ms_token"])
    if platform == "telegram":
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        return TelegramAdapter(
            api_id=stored["api_id"],
            api_hash=stored["api_hash"],
            session_path=SESSIONS_DIR / "telegram.session",
        )
    if platform == "instagram":
        if stored.get("mode") == "graph_api":
            return InstagramGraphApiAdapter(access_token=stored["graph_api_token"])
        return InstagramScrapeAdapter()

    raise ValueError(f"Неизвестная платформа: {platform}")
