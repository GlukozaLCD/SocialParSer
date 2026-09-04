"""YouTube-адаптер: голый requests к YouTube Data API v3 (без google-api-python-client —
незачем тянуть тяжёлый SDK ради двух GET-запросов)."""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from src.adapters.base import AdapterError, PostLink, PostMetrics, int_or_none
from src.config_store import WatchlistSource

CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
PAGE_SIZE = 50
MAX_PAGES = 10  # предохранитель: за сутки у канала не бывает сотен видео


class YoutubeAdapter:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def fetch_recent_posts(self, source: WatchlistSource, since: datetime) -> list[PostLink]:
        uploads_playlist_id = self._resolve_uploads_playlist(source.id)
        results: list[PostLink] = []
        page_token = None
        for _ in range(MAX_PAGES):
            data = self._get(
                PLAYLIST_ITEMS_URL,
                {
                    "part": "snippet,contentDetails",
                    "playlistId": uploads_playlist_id,
                    "maxResults": PAGE_SIZE,
                    "pageToken": page_token,
                },
            )
            items = data.get("items", [])
            reached_boundary = False
            for item in items:
                post = _item_to_post_link(item, source)
                if post.published_at < since:
                    reached_boundary = True
                    break
                results.append(post)
            page_token = data.get("nextPageToken")
            if reached_boundary or not page_token:
                break
        return results

    def fetch_post_metrics(self, public_id: str, post_id: str) -> PostMetrics:
        # videoId глобально уникален — public_id (канал) тут не нужен.
        data = self._get(VIDEOS_URL, {"part": "statistics", "id": post_id})
        items = data.get("items", [])
        if not items:
            raise AdapterError(f"YouTube: видео {post_id} не найдено")
        stats = items[0]["statistics"]
        return PostMetrics(
            views=int_or_none(stats.get("viewCount")),
            likes=int_or_none(stats.get("likeCount")),  # автор мог скрыть — тогда None
            comments=int_or_none(stats.get("commentCount")),
            reposts=None,  # у YouTube нет понятия репоста
            saves=None,  # и сохранений в API тоже нет
        )

    def fetch_subscriber_count(self, source: WatchlistSource) -> int | None:
        data = self._get(CHANNELS_URL, {"part": "statistics", **_channel_id_param(source.id)})
        items = data.get("items", [])
        if not items:
            raise AdapterError(f"YouTube: канал не найден ({source.id})")
        stats = items[0]["statistics"]
        if stats.get("hiddenSubscriberCount"):
            return None  # автор канала сам скрыл счётчик — не ошибка
        return int_or_none(stats.get("subscriberCount"))

    def _resolve_uploads_playlist(self, channel_id_or_handle: str) -> str:
        data = self._get(CHANNELS_URL, {"part": "contentDetails", **_channel_id_param(channel_id_or_handle)})
        items = data.get("items", [])
        if not items:
            raise AdapterError(f"YouTube: канал не найден ({channel_id_or_handle})")
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    def _get(self, url: str, params: dict) -> dict:
        response = requests.get(
            url,
            params={k: v for k, v in {**params, "key": self._api_key}.items() if v is not None},
            timeout=15,
        )
        if response.status_code != 200:
            message = response.json().get("error", {}).get("message", response.text)
            raise AdapterError(f"YouTube: {message}")
        return response.json()


def _channel_id_param(channel_id_or_handle: str) -> dict:
    if channel_id_or_handle.startswith("UC"):
        return {"id": channel_id_or_handle}
    return {"forHandle": channel_id_or_handle.lstrip("@")}


def _item_to_post_link(item: dict, source: WatchlistSource) -> PostLink:
    published_at = item["snippet"]["publishedAt"].replace("Z", "+00:00")
    video_id = item["contentDetails"]["videoId"]
    return PostLink(
        platform="youtube",
        public_id=source.id,
        public_name=source.display_name,
        post_url=f"https://www.youtube.com/watch?v={video_id}",
        published_at=datetime.fromisoformat(published_at).astimezone(timezone.utc),
        post_id=video_id,
    )
