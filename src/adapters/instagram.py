"""Instagram-адаптер: два независимых режима.

- graph_api — официальный Graph API для собственных Business/Creator страниц.
- scrape — вход в отдельный аккаунт через instagrapi для чтения чужих
  публичных страниц (неофициально, см. допущения в PLAN.md).

Какой класс использовать, решает src/adapters/registry.py по полю
credentials["instagram"]["mode"].
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests
from instagrapi import Client

from src.adapters.base import AdapterError, PostLink, PostMetrics
from src.config_store import SESSIONS_DIR, WatchlistSource

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"
SCRAPE_BATCH_SIZE = 50  # без глубокой пагинации — см. допущение в плане Фазы 2б


class InstagramGraphApiAdapter:
    def __init__(self, access_token: str):
        self._access_token = access_token

    def fetch_recent_posts(self, source: WatchlistSource, since: datetime) -> list[PostLink]:
        results: list[PostLink] = []
        url = f"{GRAPH_API_BASE}/{source.id}/media"
        params = {"fields": "id,permalink,timestamp", "access_token": self._access_token, "limit": 50}
        while url:
            data = self._get(url, params)
            reached_boundary = False
            for item in data.get("data", []):
                post = _graph_item_to_post_link(item, source)
                if post.published_at < since:
                    reached_boundary = True
                    break
                results.append(post)
            url = None if reached_boundary else data.get("paging", {}).get("next")
            params = None  # next-ссылка уже содержит все параметры
        return results

    def fetch_post_metrics(self, public_id: str, post_id: str) -> PostMetrics:
        # ID медиа Graph API глобально уникален — public_id тут не нужен.
        basic = self._get(f"{GRAPH_API_BASE}/{post_id}", {"fields": "like_count,comments_count"})
        likes = basic.get("like_count")
        comments = basic.get("comments_count")

        # Просмотры/сохранения/репосты — только через Insights, а это
        # отдельное право токена (instagram_manage_insights). Нет прав или
        # метрика не подходит этому типу медиа — не роняем весь пост, просто
        # оставляем эти поля пустыми, лайки/комментарии всё равно есть.
        views = saves = reposts = None
        try:
            insights = self._get(f"{GRAPH_API_BASE}/{post_id}/insights", {"metric": "saved,shares,views"})
            values = {item["name"]: item["values"][0]["value"] for item in insights.get("data", [])}
            views = values.get("views")
            saves = values.get("saved")
            reposts = values.get("shares")
        except AdapterError:
            pass

        return PostMetrics(views=views, likes=likes, comments=comments, reposts=reposts, saves=saves)

    def fetch_subscriber_count(self, source: WatchlistSource) -> int | None:
        # source.id для этого режима — числовой ID Business-аккаунта (не юзернейм).
        data = self._get(f"{GRAPH_API_BASE}/{source.id}", {"fields": "followers_count"})
        return data.get("followers_count")

    def _get(self, url: str, params: dict | None) -> dict:
        request_params = {**params, "access_token": self._access_token} if params else None
        response = requests.get(url, params=request_params, timeout=15)
        if response.status_code != 200:
            message = response.json().get("error", {}).get("message", response.text)
            raise AdapterError(f"Instagram (graph_api): {message}")
        return response.json()


class InstagramScrapeAdapter:
    def __init__(self):
        self._client: Client | None = None  # кэш на время жизни адаптера — не логинимся заново на каждый вызов

    def fetch_recent_posts(self, source: WatchlistSource, since: datetime) -> list[PostLink]:
        client = self._login()
        user_id = client.user_id_from_username(source.id)
        medias = client.user_medias(user_id, amount=SCRAPE_BATCH_SIZE)
        return [
            post
            for media in medias
            if (post := _media_to_post_link(media, source)).published_at >= since
        ]

    def fetch_post_metrics(self, public_id: str, post_id: str) -> PostMetrics:
        # media.pk глобально уникален — public_id (юзернейм) тут не нужен.
        client = self._login()
        media = client.media_info(int(post_id))
        return PostMetrics(
            views=media.view_count,  # только у видео/reels, у фото — None
            likes=media.like_count,
            comments=media.comment_count,
            reposts=None,  # неофициальному клиенту недоступно
            saves=None,  # тоже недоступно
        )

    def fetch_subscriber_count(self, source: WatchlistSource) -> int | None:
        client = self._login()
        user_id = client.user_id_from_username(source.id)
        return client.user_info(user_id).follower_count

    def _login(self) -> Client:
        if self._client is not None:
            return self._client

        # Логин по паролю здесь больше не делается — сессия устанавливается
        # один раз через видимый браузер (см. src/menu/prompts.py и
        # src/menu/instagram_browser_login.py), а тут только загружается уже
        # готовый, полностью восстанавливающий авторизацию файл сессии
        # (instagrapi.Client.load_settings() сам восстанавливает
        # authorization_data/cookies — повторный вызов login_by_sessionid()
        # не требуется).
        session_path = SESSIONS_DIR / "instagram.json"
        if not session_path.exists():
            raise AdapterError(
                "Instagram (scrape): сессия ещё не установлена — зайдите в "
                "python main.py settings и подключите Instagram (потребуется один раз "
                "войти через браузер)."
            )
        client = Client()
        client.load_settings(session_path)
        self._client = client
        return client


def _graph_item_to_post_link(item: dict, source: WatchlistSource) -> PostLink:
    published_at = datetime.strptime(item["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
    return PostLink(
        platform="instagram",
        public_id=source.id,
        public_name=source.display_name,
        post_url=item["permalink"],
        published_at=published_at.astimezone(timezone.utc),
        # Внутренний ID медиа Graph API — не то же самое, что permalink;
        # именно он понадобится для запроса метрик (Insights) позже.
        post_id=item["id"],
    )


def _media_to_post_link(media, source: WatchlistSource) -> PostLink:
    taken_at = media.taken_at
    if taken_at.tzinfo is None:
        taken_at = taken_at.replace(tzinfo=timezone.utc)
    return PostLink(
        platform="instagram",
        public_id=source.id,
        public_name=source.display_name,
        post_url=f"https://www.instagram.com/p/{media.code}/",
        published_at=taken_at,
        # media.pk (не code/shortcode) — то, что instagrapi ожидает в
        # media_info() при последующем запросе метрик.
        post_id=str(media.pk),
    )
