"""Встроенный планировщик (Этап 4.2) — для машин без внешнего Task Scheduler/cron.

Время суток — локальное, не UTC: так его понимает сам пользователь и так же
его понимают Task Scheduler/cron, которыми эта функция заменяется на других
машинах (см. README, «Автоматический запуск по расписанию»). Остальная
программа (сбор, since-фильтрация в адаптерах) внутри работает в UTC — это
не связано между собой, здесь только решается «когда пора запускать».
"""

from __future__ import annotations

import logging
import time as time_module
from datetime import datetime, timedelta
from datetime import time as time_of_day

from src.collector import run_collection
from src.metrics_collector import collect_metrics, post_link_to_ref

logger = logging.getLogger(__name__)

DEFAULT_TIME = time_of_day(9, 0)


def parse_time_of_day(value: str) -> time_of_day:
    return datetime.strptime(value, "%H:%M").time()


def seconds_until(now: datetime, at: time_of_day) -> float:
    """Секунд до ближайшего наступления `at` строго после `now` (сегодня,
    если ещё не прошло, иначе завтра). Точное совпадение считается «уже
    прошло» — иначе рискуем сработать дважды подряд на границе секунды."""
    target = datetime.combine(now.date(), at)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def run_daemon(at: time_of_day = DEFAULT_TIME) -> None:
    print(f"Встроенный планировщик запущен. Время сбора: {at.strftime('%H:%M')} (Ctrl+C — остановить).")

    now = datetime.now()
    target_today = datetime.combine(now.date(), at)
    if now >= target_today:
        print("Время сегодняшнего сбора уже прошло — собираю сразу.")
        _run_collection_safely()

    try:
        while True:
            wait_seconds = seconds_until(datetime.now(), at)
            next_run = datetime.now() + timedelta(seconds=wait_seconds)
            print(f"Следующий сбор: {next_run.strftime('%Y-%m-%d %H:%M')}.")
            logger.info("Следующий сбор запланирован на %s.", next_run.isoformat())
            time_module.sleep(wait_seconds)
            _run_collection_safely()
    except KeyboardInterrupt:
        print("\nПланировщик остановлен пользователем.")


def _run_collection_safely() -> None:
    # Если сбор упадёт по неожиданной причине (например, испортился
    # watchlist.json) — демон не должен падать целиком и ждать, пока
    # пользователь вручную его перезапустит; попробует снова на следующем цикле.
    # Ссылки и метрики — тот же единый проход, что и у run-once из cli.py.
    try:
        run = run_collection()
        collect_metrics(
            run.now.date(),
            posts=[post_link_to_ref(p) for p in run.posts],
            sources=run.sources,
            credentials=run.credentials,
        )
    except Exception:
        logger.exception("Сбор в демон-режиме упал с ошибкой — попробую снова в следующий раз.")
