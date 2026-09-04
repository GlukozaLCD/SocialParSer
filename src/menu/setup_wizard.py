"""Мастер первого запуска (Этап 1.3).

Срабатывает из main.py, когда ещё нет config/credentials.json. Заводит
учётные данные для выбранных платформ и хотя бы один паблик для отслеживания,
после чего программа переходит в тот режим, который пользователь изначально
запрашивал.
"""

from __future__ import annotations

import questionary

from src.config_store import (
    CREDENTIALS_WARNING,
    CREDENTIALS_PATH,
    save_credentials,
    save_watchlist,
)
from src.menu.prompts import (
    Cancelled,
    PlatformSetupFailed,
    prompt_credentials_for_platform,
    prompt_new_source,
    prompt_platforms_checkbox,
)
from src.platforms import platform_label


def run() -> None:
    print("Похоже, вы запускаете программу впервые — настроим источники данных.\n")

    try:
        platforms = prompt_platforms_checkbox()
        while not platforms:
            print("Нужно выбрать хотя бы одну платформу.")
            platforms = prompt_platforms_checkbox()

        # Отказ одной платформы (например, Instagram запросил подтверждение
        # через приложение) не должен обнулять уже введённые данные по
        # остальным — поэтому ловим PlatformSetupFailed на каждой отдельно,
        # а не разом на весь список.
        credentials = {}
        connected = []
        for platform in platforms:
            try:
                credentials[platform] = prompt_credentials_for_platform(platform)
                connected.append(platform)
            except PlatformSetupFailed:
                print(f"«{platform_label(platform)}» пропущена — подключите её позже через python main.py settings.\n")

        if not connected:
            print("Ни одна платформа не подключилась — настройка прервана, ничего не сохранено.")
            raise SystemExit(1)

        sources = [prompt_new_source(connected)]
        while questionary.confirm("Добавить ещё один паблик?", default=False).ask():
            sources.append(prompt_new_source(connected))
    except Cancelled:
        print("\nНастройка прервана, ничего не сохранено.")
        raise SystemExit(1)

    save_credentials(credentials)
    save_watchlist(sources)

    print(f"\nГотово. Настройки сохранены в config/.")
    print(f"ВНИМАНИЕ: {CREDENTIALS_PATH.name} — {CREDENTIALS_WARNING}\n")
