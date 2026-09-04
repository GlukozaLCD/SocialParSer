"""Общий интерфейс адаптеров платформ и единая схема результата.

PostLink — та же схема, которую Фаза 3 будет агрегировать и записывать в
файл; определена здесь, а не отложена до Фазы 3, потому что каждый адаптер
должен сразу отдавать данные в этом виде.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.config_store import WatchlistSource


@dataclass
class PostLink:
    platform: str
    public_id: str
    public_name: str
    post_url: str
    published_at: datetime  # timezone-aware, UTC
    # Сырой, специфичный для платформы идентификатор поста — нужен, чтобы
    # позже (план «сбор метрик») повторно найти этот же пост через API
    # платформы. Одного post_url для этого не всегда достаточно: например,
    # у Instagram в режиме graph_api сохраняется публичная ссылка (permalink),
    # а Graph API для запроса метрик требует внутренний ID медиа — обратного
    # пути от ссылки к этому ID через API нет.
    post_id: str


@dataclass
class PostMetrics:
    """Текущий снимок метрик поста. Не все платформы отдают все пять полей —
    чего платформа не умеет (а не просто "там ноль"), то None. См. таблицу
    в .plans/PLAN_post-metrics.md, Фаза 2."""

    views: int | None
    likes: int | None
    comments: int | None
    reposts: int | None
    saves: int | None


class PlatformAdapter(Protocol):
    def fetch_recent_posts(self, source: WatchlistSource, since: datetime) -> list[PostLink]: ...

    def fetch_post_metrics(self, public_id: str, post_id: str) -> PostMetrics: ...

    def fetch_subscriber_count(self, source: WatchlistSource) -> int | None: ...


class AdapterError(Exception):
    """Платформа ответила ошибкой или запрос не удался (сеть, HTTP-статус и т.п.).

    Не путать с config_store.MissingCredentialsError — та про нехватку
    токенов до обращения к платформе, эта — про сам обмен с платформой.
    """


def int_or_none(value) -> int | None:
    """Платформы то отдают числовые поля строками, то не отдают их вовсе."""
    return None if value is None else int(value)
