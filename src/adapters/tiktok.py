"""TikTok-адаптер: TikTokApi поверх Playwright.

TikTokApi асинхронная (весь остальной код программы — синхронный), поэтому
наружу торчит обычный синхронный fetch_recent_posts, а асинхронность спрятана
внутри через asyncio.run — не заражает асинхронностью остальной проект.

Портативность: браузер Playwright по умолчанию ставится в системный кэш
пользователя — переопределяем на папку внутри проекта (то же самое должен
сделать setup.bat/setup.sh перед `playwright install chromium`, иначе браузер
при запуске и при установке окажется в разных местах).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from src.config_store import PROJECT_ROOT, WatchlistSource
from src.adapters.base import AdapterError, PostLink, PostMetrics, int_or_none

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(PROJECT_ROOT / ".playwright-browsers"))

from TikTokApi import TikTokApi  # noqa: E402 (после выставления PLAYWRIGHT_BROWSERS_PATH)

BATCH_SIZE = 30  # без глубокой пагинации — как и в Instagram-scrape


class TikTokAdapter:
    def __init__(self, ms_token: str):
        self._ms_token = ms_token

    def fetch_recent_posts(self, source: WatchlistSource, since: datetime) -> list[PostLink]:
        return asyncio.run(self._fetch_async(source, since))

    async def _fetch_async(self, source: WatchlistSource, since: datetime) -> list[PostLink]:
        results: list[PostLink] = []
        async with TikTokApi() as api:
            await api.create_sessions(ms_tokens=[self._ms_token], num_sessions=1, headless=True)
            user = api.user(username=source.id)
            async for video in user.videos(count=BATCH_SIZE):
                post = _video_to_post_link(video.as_dict, source)
                if post.published_at >= since:
                    results.append(post)
        return results

    def fetch_post_metrics(self, public_id: str, post_id: str) -> PostMetrics:
        # ID видео глобально уникален — public_id (юзернейм) тут не нужен.
        # Как и в fetch_recent_posts, отдельная браузерная сессия на вызов —
        # неэффективно при большом числе постов за раз, но TikTokApi не даёт
        # простого способа переиспользовать сессию между отдельными
        # asyncio.run(); можно будет оптимизировать позже при необходимости.
        return asyncio.run(self._fetch_metrics_async(post_id))

    async def _fetch_metrics_async(self, post_id: str) -> PostMetrics:
        async with TikTokApi() as api:
            await api.create_sessions(ms_tokens=[self._ms_token], num_sessions=1, headless=True)
            data = await api.video(id=post_id).info()
        stats = data.get("statsV2") or data.get("stats")
        if not stats:
            raise AdapterError(f"TikTok: видео {post_id} не найдено")
        return _stats_to_post_metrics(stats)

    def fetch_subscriber_count(self, source: WatchlistSource) -> int | None:
        return asyncio.run(self._fetch_subscriber_count_async(source))

    async def _fetch_subscriber_count_async(self, source: WatchlistSource) -> int | None:
        async with TikTokApi() as api:
            await api.create_sessions(ms_tokens=[self._ms_token], num_sessions=1, headless=True)
            info = await api.user(username=source.id).info()
        # Форма ответа менялась между версиями TikTokApi/веб-API — пробуем
        # известные варианты вместо жёсткой привязки к одной структуре.
        stats = (info.get("userInfo") or {}).get("stats") or info.get("stats") or info.get("statsV2") or {}
        return int_or_none(stats.get("followerCount"))


def _video_to_post_link(video_data: dict, source: WatchlistSource) -> PostLink:
    return PostLink(
        platform="tiktok",
        public_id=source.id,
        public_name=source.display_name,
        post_url=f"https://www.tiktok.com/@{source.id}/video/{video_data['id']}",
        published_at=datetime.fromtimestamp(video_data["createTime"], tz=timezone.utc),
        post_id=str(video_data["id"]),
    )


def _stats_to_post_metrics(stats: dict) -> PostMetrics:
    # TikTok — единственная платформа, которая честно отдаёт все пять метрик,
    # включая репосты (shareCount) и сохранения (collectCount).
    return PostMetrics(
        views=int_or_none(stats.get("playCount")),
        likes=int_or_none(stats.get("diggCount")),
        comments=int_or_none(stats.get("commentCount")),
        reposts=int_or_none(stats.get("shareCount")),
        saves=int_or_none(stats.get("collectCount")),
    )
