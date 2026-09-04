"""Оркестровка Фазы 3: пройтись по watchlist, собрать посты со всех адаптеров,
сгруппировать по пабликам, записать результат.

Падение одной платформы (просроченный токен и т.п.) не должно останавливать
сбор по остальным — это фоновая ежедневная задача, а не операция, где частичный
результат означает провал всего прохода.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.adapters.base import PlatformAdapter, PostLink
from src.adapters.registry import get_adapter
from src.config_store import MissingCredentialsError, WatchlistSource, load_credentials, load_watchlist
from src.output_writer import write_result

logger = logging.getLogger(__name__)

WINDOW_HOURS = 24


@dataclass
class CollectionRun:
    """Результат run_collection() вместе с сырыми данными, из которых он
    собран — чтобы run-once мог сразу передать их в сбор метрик (Фаза 4
    плана «сбор метрик»), не перечитывая только что записанный файл с диска."""

    result: dict
    posts: list[PostLink]
    sources: list[WatchlistSource]  # только те, что успешно собрались
    credentials: dict
    now: datetime


def run_collection(now: datetime | None = None) -> CollectionRun:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=WINDOW_HOURS)

    sources = load_watchlist()
    credentials = load_credentials()

    adapters_cache: dict[str, PlatformAdapter] = {}
    adapter_errors: dict[str, str] = {}  # платформа -> причина, чтобы не пытаться повторно на каждом её паблике
    errors: list[dict] = []
    succeeded_sources: list[WatchlistSource] = []
    all_posts: list[PostLink] = []

    for source in sources:
        if source.platform in adapter_errors:
            errors.append(
                {"platform": source.platform, "public_id": source.id, "message": adapter_errors[source.platform]}
            )
            continue

        adapter = adapters_cache.get(source.platform)
        if adapter is None:
            try:
                adapter = get_adapter(source.platform, credentials)
                adapters_cache[source.platform] = adapter
            except MissingCredentialsError as exc:
                message = str(exc)
                adapter_errors[source.platform] = message
                errors.append({"platform": source.platform, "public_id": source.id, "message": message})
                logger.warning("Пропускаю платформу %s: %s", source.platform, message)
                continue

        try:
            posts = adapter.fetch_recent_posts(source, since)
        except Exception as exc:  # адаптер может упасть по сети/API — не должно ронять весь проход
            message = str(exc)
            errors.append({"platform": source.platform, "public_id": source.id, "message": message})
            logger.warning("Не удалось собрать %s/%s: %s", source.platform, source.id, message)
            continue

        all_posts.extend(posts)
        succeeded_sources.append(source)

    # "status" — не про код выхода (тот всегда 0, так решил пользователь: это
    # фоновая ежедневная задача, а не операция, которая должна падать целиком
    # из-за одной платформы), а про то, можно ли доверять результату как полному.
    # Кто угодно, кому это важно — другой процесс, сам пользователь, будущий
    # сетевой приёмник — может проверить это поле или errors, не завязываясь
    # на exit code.
    status = "partial" if errors else "ok"
    result = {
        "generated_at": now.isoformat(),
        "window_hours": WINDOW_HOURS,
        "status": status,
        "publics": group_posts_by_public(all_posts, succeeded_sources),
        "errors": errors,
    }

    if errors:
        logger.warning(
            "Частичный сбор: %d из %d источников не отдали данные (см. 'errors' в файле результата).",
            len(errors),
            len(sources),
        )
    else:
        logger.info("Сбор завершён без ошибок.")

    path = write_result(result, now.date())
    _print_summary(result, path)
    return CollectionRun(
        result=result, posts=all_posts, sources=succeeded_sources, credentials=credentials, now=now
    )


def group_posts_by_public(posts: list[PostLink], sources: list[WatchlistSource]) -> list[dict]:
    """Группирует посты по пабликам в порядке watchlist, посты внутри — от новых к старым."""
    posts_by_key: dict[tuple[str, str], list[PostLink]] = {}
    for post in posts:
        posts_by_key.setdefault((post.platform, post.public_id), []).append(post)

    groups = []
    for source in sources:
        group_posts = sorted(
            posts_by_key.get((source.platform, source.id), []),
            key=lambda p: p.published_at,
            reverse=True,
        )
        groups.append(
            {
                "platform": source.platform,
                "public_id": source.id,
                "public_name": source.display_name,
                "posts": [
                    {
                        "post_id": p.post_id,
                        "post_url": p.post_url,
                        "published_at": p.published_at.isoformat(),
                    }
                    for p in group_posts
                ],
            }
        )
    return groups


def _print_summary(result: dict, path: Path) -> None:
    total_posts = sum(len(p["posts"]) for p in result["publics"])
    print(f"Собрано {total_posts} постов из {len(result['publics'])} пабликов. Статус: {result['status']}.")
    if result["errors"]:
        print(f"Не собралось ({len(result['errors'])}):")
        for err in result["errors"]:
            print(f"  {err['platform']}/{err['public_id']} — {err['message']}")
    print(f"Результат: {path}")
