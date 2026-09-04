"""Разбор команд и диспетчеризация. main.py вызывает build_parser()/dispatch()."""

from __future__ import annotations

import argparse
import logging
from datetime import date

from src.collector import run_collection
from src.menu import settings_menu
from src.metrics_collector import LinksFileNotFound, collect_metrics, post_link_to_ref
from src.scheduler import DEFAULT_TIME, parse_time_of_day, run_daemon

logger = logging.getLogger(__name__)

AVAILABLE_COMMANDS = "settings, run-once, run-daemon, collect-metrics"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Сборщик данных соцсетей (VK/Telegram/YouTube/Instagram/TikTok).",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("settings", help="Список пабликов и учётные данные платформ")

    run_once_parser = subparsers.add_parser(
        "run-once", help="Один проход: ссылки + метрики постов + подписчики"
    )
    run_once_parser.add_argument(
        "--skip-metrics", action="store_true", help="не собирать метрики постов в этом запуске"
    )
    run_once_parser.add_argument(
        "--skip-subscribers", action="store_true", help="не собирать число подписчиков в этом запуске"
    )

    daemon_parser = subparsers.add_parser("run-daemon", help="Встроенный планировщик: сбор раз в сутки")
    daemon_parser.add_argument(
        "--at",
        type=_parse_time_arg,
        default=DEFAULT_TIME,
        metavar="ЧЧ:ММ",
        help=f"время сбора (локальное), по умолчанию {DEFAULT_TIME.strftime('%H:%M')}",
    )

    metrics_parser = subparsers.add_parser(
        "collect-metrics",
        help="Пересчитать метрики/подписчиков по уже собранным ссылкам (без нового run-once)",
    )
    metrics_parser.add_argument(
        "--date",
        type=_parse_date_arg,
        default=None,
        metavar="ГГГГ-ММ-ДД",
        help="за какую дату (по умолчанию сегодня); нужен уже существующий links_<дата>.json",
    )

    return parser


def _parse_time_arg(value: str):
    try:
        return parse_time_of_day(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"неверный формат времени «{value}», ожидается ЧЧ:ММ (например, 09:00)")


def _parse_date_arg(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"неверный формат даты «{value}», ожидается ГГГГ-ММ-ДД")


def dispatch(args: argparse.Namespace) -> None:
    if args.command == "settings":
        settings_menu.run()
    elif args.command == "run-once":
        logger.info("run-once: начинаю сбор.")
        run = run_collection()
        if not (args.skip_metrics and args.skip_subscribers):
            collect_metrics(
                run.now.date(),
                posts=[post_link_to_ref(p) for p in run.posts],
                sources=run.sources,
                credentials=run.credentials,
                skip_metrics=args.skip_metrics,
                skip_subscribers=args.skip_subscribers,
            )
    elif args.command == "run-daemon":
        logger.info("run-daemon: запускаю встроенный планировщик (%s).", args.at.strftime("%H:%M"))
        run_daemon(args.at)
    elif args.command == "collect-metrics":
        target_date = args.date or date.today()
        try:
            collect_metrics(target_date)
        except LinksFileNotFound as exc:
            print(str(exc))
    else:
        print(f"Команда не указана. Доступные команды: {AVAILABLE_COMMANDS}")
        print("Пример: python main.py settings")
