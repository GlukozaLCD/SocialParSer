"""Запись результатов сбора в файл — человекочитаемый JSON, который можно
открыть и посмотреть напрямую (см. допущения в PLAN.md про выдачу результата).

Два вида файлов на один день: links_<дата>.json (ссылки, Фаза 3 первого
плана) и metrics_<дата>.json (метрики постов + подписчики, Фаза 4 второго
плана) — общая механика записи, разные имена и разное содержимое."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.config_store import PROJECT_ROOT

OUTPUT_DIR = PROJECT_ROOT / "data" / "output"


def links_output_path(day: date) -> Path:
    return OUTPUT_DIR / f"links_{day.isoformat()}.json"


def metrics_output_path(day: date) -> Path:
    return OUTPUT_DIR / f"metrics_{day.isoformat()}.json"


def write_json(result: dict, path: Path) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_result(result: dict, day: date) -> Path:
    return write_json(result, links_output_path(day))


def write_metrics_result(result: dict, day: date) -> Path:
    return write_json(result, metrics_output_path(day))
