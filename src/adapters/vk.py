"""VK-адаптер: wall.get напрямую через requests (SDK не нужен, API простой)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import requests

from src.adapters.base import AdapterError, PostLink, PostMetrics
from src.config_store import WatchlistSource

API_URL = "https://api.vk.com/method/wall.get"
METRICS_API_URL = "https://api.vk.com/method/wall.getById"
GROUPS_URL = "https://api.vk.com/method/groups.getById"
API_VERSION = "5.199"
PAGE_SIZE = 100
MAX_PAGES = 10  # предохранитель: за сутки у паблика не бывает тысяч постов

_NUMERIC_ID_RE = re.compile(r"^-?\d+$")


class VkAdapter:
    def __init__(self, access_token: str):
        self._access_token = access_token

    def fetch_recent_posts(self, source: WatchlistSource, since: datetime) -> list[PostLink]:
        params = self._owner_params(source.id)
        results: list[PostLink] = []
        offset = 0
        for _ in range(MAX_PAGES):
            data = self._request(params, offset)
            items = data.get("items", [])
            if not items:
                break
            reached_boundary = False
            for item in items:
                post = _item_to_post_link(item, source)
                if post.published_at < since:
                    reached_boundary = True
                    break
                results.append(post)
            if reached_boundary or len(items) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return results

    def fetch_post_metrics(self, public_id: str, post_id: str) -> PostMetrics:
        # post_id уже в формате "owner_id_post_id" (см. _item_to_post_link) —
        # ровно то, что ожидает wall.getById; public_id тут не нужен.
        response = self._call(METRICS_API_URL, {"posts": post_id})
        items = response if isinstance(response, list) else []
        if not items:
            raise AdapterError(f"VK: пост {post_id} не найден (удалён или недоступен)")
        return _item_to_post_metrics(items[0])

    def fetch_subscriber_count(self, source: WatchlistSource) -> int | None:
        # groups.getById не принимает owner_id в формате "-123" — только
        # положительный числовой ID или screen name.
        group_id = source.id.lstrip("-")
        response = self._call(GROUPS_URL, {"group_id": group_id, "fields": "members_count"})
        groups = response.get("groups", []) if isinstance(response, dict) else response
        if not groups:
            raise AdapterError(f"VK: паблик {source.id} не найден")
        return groups[0].get("members_count")

    def _owner_params(self, source_id: str) -> dict:
        if _NUMERIC_ID_RE.match(source_id):
            return {"owner_id": -abs(int(source_id))}
        return {"domain": source_id}

    def _request(self, owner_params: dict, offset: int) -> dict:
        return self._call(API_URL, {**owner_params, "count": PAGE_SIZE, "offset": offset})

    def _call(self, url: str, params: dict):
        response = requests.get(
            url,
            params={**params, "access_token": self._access_token, "v": API_VERSION},
            timeout=15,
        )
        body = response.json()
        if "error" in body:
            raise AdapterError(f"VK: {body['error'].get('error_msg', body['error'])}")
        return body.get("response", {})


def _item_to_post_link(item: dict, source: WatchlistSource) -> PostLink:
    owner_id = item["owner_id"]
    numeric_id = item["id"]
    return PostLink(
        platform="vk",
        public_id=source.id,
        public_name=source.display_name,
        post_url=f"https://vk.com/wall{owner_id}_{numeric_id}",
        published_at=datetime.fromtimestamp(item["date"], tz=timezone.utc),
        # Тот же формат "owner_id_post_id", что ожидает wall.getById —
        # пригодится для сбора метрик без повторного парсинга ссылки.
        post_id=f"{owner_id}_{numeric_id}",
    )


def _item_to_post_metrics(item: dict) -> PostMetrics:
    # VK не отдаёт число сохранений поста через API вообще — saves всегда None.
    return PostMetrics(
        views=item.get("views", {}).get("count"),
        likes=item.get("likes", {}).get("count"),
        comments=item.get("comments", {}).get("count"),
        reposts=item.get("reposts", {}).get("count"),
        saves=None,
    )
