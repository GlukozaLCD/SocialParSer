"""Настройка логирования: консоль + обычный файл + подробный debug-файл.

Лог-файл нужен, чтобы падение ночного автоматического запуска (run-daemon
или запуск из Task Scheduler/cron) было видно постфактум, а не терялось
вместе с закрывшимся окном консоли.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from src.config_store import PROJECT_ROOT

LOG_DIR = PROJECT_ROOT / "data" / "logs"
LOG_PATH = LOG_DIR / "parser.log"

# Отдельная папка для подробных технических логов (уровень DEBUG — запросы к
# API платформ, служебные детали библиотек и т.п.). Специально не рядом с
# обычным parser.log: в debug-логе может засветиться то, что не хочется
# случайно унести при передаче папки проекта другому человеку — реальные
# логины/юзернеймы отслеживаемых или подключаемых аккаунтов, IP-адреса,
# отпечатки устройств. Всю эту папку нужно удалять перед передачей — см.
# README, «Перед тем как передать программу другому человеку».
DEBUG_LOG_DIR = PROJECT_ROOT / "data" / "debug_logs"
DEBUG_LOG_PATH = DEBUG_LOG_DIR / "debug.log"


class _ConsoleFormatter(logging.Formatter):
    """Как обычный форматтер, но без трейсбека — тот и так уходит в файл,
    а на экране постороннему пользователю нужна только короткая строка."""

    def formatException(self, ei) -> str:
        return ""


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

    # 1 МБ x 3 бэкапа — лог не растёт бесконечно на ежедневных запусках.
    file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(fmt))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(_ConsoleFormatter(fmt))

    # Уровень DEBUG — сюда попадает всё, включая то, что молчат обычные
    # INFO-логи: полные детали запросов к API платформ (в т.ч. библиотек
    # вроде instagrapi/urllib3). Именно это нужно для разбора вроде "почему
    # Instagram не пускает" — но именно поэтому файл живёт отдельно и должен
    # удаляться перед передачей проекта.
    debug_file_handler = RotatingFileHandler(
        DEBUG_LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    debug_file_handler.setLevel(logging.DEBUG)
    debug_file_handler.setFormatter(logging.Formatter(fmt))

    root = logging.getLogger()
    # Сам root должен пропускать DEBUG, иначе debug_file_handler ничего не
    # увидит — фильтрация по уровню происходит и на root, и на хендлерах;
    # реальную "громкость" каждого назначения задают их собственные setLevel.
    root.setLevel(logging.DEBUG)
    # Порядок важен: logging кеширует отформатированный traceback на самой
    # записи (record.exc_text) при первом обращении. Консольный обработчик
    # должен сработать первым и закешировать пустую строку (наш формат без
    # трейсбека) — тогда файловый обработчик увидит пустой кеш и посчитает
    # traceback заново уже своим (полным) форматтером.
    root.addHandler(console_handler)
    root.addHandler(file_handler)
    root.addHandler(debug_file_handler)
