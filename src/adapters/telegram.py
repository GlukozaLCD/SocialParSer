"""Telegram-адаптер: Telethon в синхронном режиме (telethon.sync) — весь
остальной код программы синхронный, отдельного asyncio не заводим.

Сессия должна быть заведена заранее (см. src/menu/prompts.py — одноразовый
интерактивный вход при вводе учётных данных Telegram). Здесь её только
переиспользуем.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from telethon.sync import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest

from src.adapters.base import AdapterError, PostLink, PostMetrics
from src.config_store import WatchlistSource


class TelegramAdapter:
    def __init__(self, api_id: str, api_hash: str, session_path: Path):
        self._api_id = int(api_id)
        self._api_hash = api_hash
        self._session_path = session_path

    def fetch_recent_posts(self, source: WatchlistSource, since: datetime) -> list[PostLink]:
        results: list[PostLink] = []
        with TelegramClient(str(self._session_path), self._api_id, self._api_hash) as client:
            for message in client.iter_messages(source.id, limit=None):
                if message.date < since:
                    break
                post = _message_to_post_link(message, source)
                if post is not None:
                    results.append(post)
        return results

    def fetch_post_metrics(self, public_id: str, post_id: str) -> PostMetrics:
        # В отличие от VK/YouTube, message.id уникален только внутри канала —
        # без public_id (юзернейма) сообщение не найти.
        with TelegramClient(str(self._session_path), self._api_id, self._api_hash) as client:
            message = client.get_messages(public_id, ids=int(post_id))
        if message is None:
            raise AdapterError(f"Telegram: сообщение {post_id} в {public_id} не найдено")
        return _message_to_post_metrics(message)

    def fetch_subscriber_count(self, source: WatchlistSource) -> int | None:
        with TelegramClient(str(self._session_path), self._api_id, self._api_hash) as client:
            full = client(GetFullChannelRequest(source.id))
        return full.full_chat.participants_count


def _message_to_post_link(message, source: WatchlistSource) -> PostLink | None:
    if message.action is not None:
        # служебное сообщение (кто-то вступил/вышел и т.п.) — не пост
        return None
    return PostLink(
        platform="telegram",
        public_id=source.id,
        public_name=source.display_name,
        post_url=f"https://t.me/{source.id}/{message.id}",
        published_at=message.date,
        post_id=str(message.id),
    )


def _message_to_post_metrics(message) -> PostMetrics:
    # У каналов нет ни "лайков" в привычном смысле (только реакции, если
    # включены — их и суммируем как замену), ни программного доступа к
    # комментариям (это отдельный привязанный чат), ни сохранений.
    likes = None
    if message.reactions is not None:
        likes = sum(r.count for r in message.reactions.results)
    return PostMetrics(
        views=message.views,
        likes=likes,
        comments=None,
        reposts=message.forwards,
        saves=None,
    )
