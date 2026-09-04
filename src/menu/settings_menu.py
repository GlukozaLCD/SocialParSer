"""Меню настроек (Этап 1.4) — доступно в любой момент через `python main.py settings`.

Просто оболочка над src.config_store: своей логики валидации не содержит,
только чтение/запись через load_*/save_* и вопросы пользователю.
"""

from __future__ import annotations

import questionary

from src.config_store import (
    CREDENTIALS_WARNING,
    has_session,
    load_credentials,
    load_watchlist,
    reset_session,
    save_credentials,
    save_watchlist,
    session_exists,
    validate,
)
from src.menu.prompts import Cancelled, PlatformSetupFailed, prompt_credentials_for_platform, prompt_new_source
from src.platforms import PLATFORMS, missing_credential_fields, platform_label


def run() -> None:
    try:
        while True:
            choice = questionary.select(
                "Меню настроек:",
                choices=[
                    questionary.Choice("Паблики", value="sources"),
                    questionary.Choice("Учётные данные", value="credentials"),
                    questionary.Choice("Проверить готовность к запуску", value="check"),
                    questionary.Choice("Выход", value="exit"),
                ],
            ).ask()
            if choice is None or choice == "exit":
                return
            if choice == "sources":
                _manage_sources()
            elif choice == "credentials":
                _manage_credentials()
            elif choice == "check":
                _check_readiness()
    except Cancelled:
        return


def _check_readiness() -> None:
    sources = load_watchlist()
    if not sources:
        print("Список пабликов пуст — добавьте хотя бы один в разделе «Паблики».")
        return
    problems = validate(sources, load_credentials())
    if not problems:
        print("Всё готово: все платформы из списка пабликов подключены. Можно запускать run-once.")
        return
    print(f"Не готово ({len(problems)}):")
    for problem in problems:
        print(f"  {problem}")


def _manage_sources() -> None:
    while True:
        sources = load_watchlist()
        lines = [
            f"{s.display_name} ({platform_label(s.platform)}, id={s.id})" for s in sources
        ]
        action = questionary.select(
            "Паблики:",
            choices=[
                *[questionary.Choice(line, value=("noop", i)) for i, line in enumerate(lines)],
                questionary.Choice("+ Добавить паблик", value=("add", None)),
                questionary.Choice("Удалить паблик...", value=("delete", None)),
                questionary.Choice("Назад", value=("back", None)),
            ],
        ).ask()
        if action is None or action[0] == "back":
            return

        kind, index = action
        if kind == "add":
            sources.append(prompt_new_source(list(PLATFORMS.keys())))
            save_watchlist(sources)
        elif kind == "delete":
            if not sources:
                print("Список пуст.")
                continue
            target = questionary.select(
                "Какой паблик удалить?",
                choices=[questionary.Choice(line, value=i) for i, line in enumerate(lines)],
            ).ask()
            if target is None:
                continue
            removed = sources.pop(target)
            save_watchlist(sources)
            print(f"Удалено: {removed.display_name}")
        # kind == "noop" -> просто пункт списка для обзора, редактирование не сделано
        # отдельным пунктом, чтобы не плодить лишний UI ради Фазы 1; при
        # необходимости правки проще удалить и добавить заново.


def _manage_credentials() -> None:
    while True:
        credentials = load_credentials()
        choices = []
        for key in PLATFORMS:
            connected = _is_connected(key, credentials)
            status = "подключена" if connected else "не подключена"
            choices.append(questionary.Choice(f"{platform_label(key)} — {status}", value=key))
        choices.append(questionary.Choice("Назад", value=None))

        platform = questionary.select("Учётные данные платформ:", choices=choices).ask()
        if platform is None:
            return

        connected = _is_connected(platform, credentials)
        if not connected:
            entry_choices = [questionary.Choice("Ввести данные", value="enter")]
            if has_session(platform):
                entry_choices.append(questionary.Choice("Сбросить сессию/устройство", value="reset"))
            entry_choices.append(questionary.Choice("Назад", value="back"))

            action = questionary.select(f"{platform_label(platform)} не подключена:", choices=entry_choices).ask()
            if action is None or action == "back":
                continue
            if action == "reset":
                _reset_session_with_message(platform)
                continue

            try:
                credentials[platform] = prompt_credentials_for_platform(platform)
            except PlatformSetupFailed:
                continue  # сообщение уже напечатано внутри — просто возвращаемся к списку платформ
            save_credentials(credentials)
            print(f"ВНИМАНИЕ: {CREDENTIALS_WARNING}")
            continue

        choices = [questionary.Choice("Изменить", value="edit")]
        if has_session(platform):
            choices.append(questionary.Choice("Сбросить сессию/устройство", value="reset"))
        choices.append(questionary.Choice("Отключить", value="disconnect"))
        choices.append(questionary.Choice("Назад", value="back"))

        action = questionary.select(f"{platform_label(platform)} уже подключена:", choices=choices).ask()
        if action == "edit":
            try:
                credentials[platform] = prompt_credentials_for_platform(
                    platform, existing=credentials.get(platform)
                )
            except PlatformSetupFailed:
                continue
            save_credentials(credentials)
        elif action == "reset":
            _reset_session_with_message(platform)
        elif action == "disconnect":
            if questionary.confirm(f"Точно отключить {platform_label(platform)}?", default=False).ask():
                credentials.pop(platform, None)
                save_credentials(credentials)


def _reset_session_with_message(platform: str) -> None:
    if reset_session(platform):
        print(
            f"Сессия «{platform_label(platform)}» сброшена. Логин/пароль или api_id/api_hash "
            f"из credentials.json не тронуты — при следующем входе будет заведено новое "
            f"устройство/сессия с нуля."
        )
    else:
        print(f"Сохранённой сессии для «{platform_label(platform)}» не было — нечего сбрасывать.")


def _is_connected(platform: str, credentials: dict) -> bool:
    stored = credentials.get(platform, {})
    if missing_credential_fields(platform, stored):
        return False
    if platform == "instagram" and stored.get("mode") == "scrape":
        # credentials.json тут может «врать»: пароль больше не хранится и не
        # проверяется, поэтому единственный надёжный признак готовности —
        # реально сохранённая браузером сессия (её могли сбросить отдельно
        # через «Сбросить сессию/устройство», не трогая credentials.json).
        return session_exists("instagram")
    return True
