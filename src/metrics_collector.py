"""Оркестровка Фазы 4 плана «сбор метрик постов и подписчиков»: по списку
постов — метрики каждого, по watchlist — число подписчиков.

Основной путь — вызывается прямо из run-once (src/cli.py) с уже собранными в
памяти данными (посты, источники, credentials), не трогая диск. Отдельная
команда collect-metrics передаёт None — тогда данные читаются из уже
записанного data/output/links_<дата>.json.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from src.adapters.base import PlatformAdapter, PostLink
from src.adapters.registry import get_adapter
from src.config_store import MissingCredentialsError, WatchlistSource, load_credentials, load_watchlist
from src.output_writer import links_output_path, write_metrics_result

logger = logging.getLogger(__name__)


@dataclass
class PostRef:
    """Минимум, нужный для запроса метрик поста — не полноценный PostLink
    (тому ещё нужны public_name/published_at, которые здесь не при делах)."""

    platform: str
    public_id: str
    post_id: str
    post_url: str


class LinksFileNotFound(Exception):
    """Нет data/output/links_<дата>.json за нужную дату — сначала нужен run-once."""


def post_link_to_ref(post: PostLink) -> PostRef:
    return PostRef(platform=post.platform, public_id=post.public_id, post_id=post.post_id, post_url=post.post_url)


def collect_metrics(
    for_date: date,
    *,
    posts: list[PostRef] | None = None,
    sources: list[WatchlistSource] | None = None,
    credentials: dict | None = None,
    skip_metrics: bool = False,
    skip_subscribers: bool = False,
) -> dict:
    if posts is None:
        posts = _load_post_refs_from_file(for_date)
    if sources is None:
        sources = load_watchlist()
    if credentials is None:
        credentials = load_credentials()

    adapters_cache: dict[str, PlatformAdapter] = {}
    adapter_errors: dict[str, str] = {}  # платформа -> причина, чтобы не пытаться повторно на каждом её посте/паблике
    errors: list[dict] = []
    post_metrics: list[dict] = []
    subscriber_counts: list[dict] = []

    def resolve_adapter(platform: str) -> PlatformAdapter | None:
        if platform in adapter_errors:
            return None
        adapter = adapters_cache.get(platform)
        if adapter is None:
            try:
                adapter = get_adapter(platform, credentials)
                adapters_cache[platform] = adapter
            except MissingCredentialsError as exc:
                adapter_errors[platform] = str(exc)
                return None
        return adapter

    if not skip_metrics:
        for post in posts:
            adapter = resolve_adapter(post.platform)
            if adapter is None:
                errors.append(
                    {"platform": post.platform, "post_id": post.post_id, "message": adapter_errors[post.platform]}
                )
                continue
            try:
                metrics = adapter.fetch_post_metrics(post.public_id, post.post_id)
            except Exception as exc:  # сеть/API конкретного поста — не должно ронять остальные
                errors.append({"platform": post.platform, "post_id": post.post_id, "message": str(exc)})
                logger.warning("Не удалось собрать метрики %s/%s: %s", post.platform, post.post_id, exc)
                continue
            post_metrics.append(
                {
                    "platform": post.platform,
                    "post_id": post.post_id,
                    "post_url": post.post_url,
                    "views": metrics.views,
                    "likes": metrics.likes,
                    "comments": metrics.comments,
                    "reposts": metrics.reposts,
                    "saves": metrics.saves,
                }
            )

    if not skip_subscribers:
        for source in sources:
            adapter = resolve_adapter(source.platform)
            if adapter is None:
                errors.append(
                    {"platform": source.platform, "public_id": source.id, "message": adapter_errors[source.platform]}
                )
                continue
            try:
                subscribers = adapter.fetch_subscriber_count(source)
            except Exception as exc:
                errors.append({"platform": source.platform, "public_id": source.id, "message": str(exc)})
                logger.warning("Не удалось собрать подписчиков %s/%s: %s", source.platform, source.id, exc)
                continue
            subscriber_counts.append(
                {
                    "platform": source.platform,
                    "public_id": source.id,
                    "public_name": source.display_name,
                    "subscribers": subscribers,
                }
            )

    status = "partial" if errors else "ok"
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "for_date": for_date.isoformat(),
        "status": status,
        "post_metrics": post_metrics,
        "subscriber_counts": subscriber_counts,
        "errors": errors,
    }

    if errors:
        logger.warning(
            "Частичный сбор метрик: %d ошибок (см. 'errors' в файле результата).", len(errors)
        )
    else:
        logger.info("Сбор метрик завершён без ошибок.")

    path = write_metrics_result(result, for_date)
    _print_summary(result, path)
    return result


def _load_post_refs_from_file(for_date: date) -> list[PostRef]:
    path = links_output_path(for_date)
    if not path.exists():
        raise LinksFileNotFound(
            f"Нет {path.name} — сначала запустите python main.py run-once (за эту дату сбор ещё не проводился)."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    refs = []
    for public in data.get("publics", []):
        for post in public.get("posts", []):
            refs.append(
                PostRef(
                    platform=public["platform"],
                    public_id=public["public_id"],
                    post_id=post["post_id"],
                    post_url=post["post_url"],
                )
            )
    return refs


def _print_summary(result: dict, path: Path) -> None:
    print(
        f"Метрик собрано: {len(result['post_metrics'])} постов, "
        f"{len(result['subscriber_counts'])} пабликов с подписчиками. Статус: {result['status']}."
    )
    if result["errors"]:
        print(f"Не собралось ({len(result['errors'])}):")
        for err in result["errors"]:
            target = err.get("post_id") or err.get("public_id")
            print(f"  {err['platform']}/{target} — {err['message']}")
    print(f"Результат: {path}")
