"""Единственная точка входа: python main.py <command>.

Лежит в корне проекта и импортирует src/ как обычный пакет — Python сам
добавляет каталог этого файла в sys.path, поэтому запуск работает из любой
скопированной папки без установки пакета и без PYTHONPATH (портативность).
"""

import sys
from pathlib import Path


def _force_utf8_console() -> None:
    # На Windows вывод в консоль иногда попадает не в реальный терминал, а в
    # перенаправленный поток с другой кодировкой по умолчанию — тогда русский
    # текст превращается в кракозябры. Явно фиксируем UTF-8 для стабильного
    # результата на любой машине. Вызывается максимально рано — даже до
    # проверки venv ниже, чтобы её сообщения тоже не портились.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_force_utf8_console()


def _venv_python_path() -> Path:
    project_root = Path(__file__).resolve().parent
    if sys.platform == "win32":
        return project_root / ".venv" / "Scripts" / "python.exe"
    return project_root / ".venv" / "bin" / "python"


def _check_running_inside_venv() -> None:
    # Все сторонние библиотеки (questionary, requests, telethon и т.д.)
    # стоят только внутри .venv/ — если запустить системным "python" вместо
    # ".venv/.../python", импорт любого из них упадёт с ModuleNotFoundError
    # и голым traceback, который постороннему пользователю ничего не скажет.
    # Проверяем это ДО импорта src.cli (там и начинаются сторонние зависимости),
    # используя только stdlib — сама эта проверка не должна ни от чего зависеть.
    venv_python = _venv_python_path()

    if not venv_python.exists():
        print(
            "Виртуальное окружение ещё не создано.\n"
            "Сначала запустите setup.bat (Windows) или setup.sh (Linux/macOS) в папке проекта."
        )
        raise SystemExit(1)

    if Path(sys.executable).resolve() != venv_python.resolve():
        print(
            "Похоже, программа запущена не через своё виртуальное окружение — часть "
            "библиотек не найдётся.\n"
            f"Используйте вместо \"python\":\n  {venv_python}\n\n"
            f'Например: "{venv_python}" {" ".join(sys.argv)}'
        )
        raise SystemExit(1)


_check_running_inside_venv()

import logging  # noqa: E402 (после проверки venv — она должна отработать первой)

from src.cli import build_parser, dispatch
from src.config_store import is_configured
from src.logging_setup import setup_logging
from src.menu import setup_wizard


def main() -> None:
    setup_logging()

    parser = build_parser()
    args = parser.parse_args()

    try:
        if not is_configured():
            setup_wizard.run()
        dispatch(args)
    except SystemExit:
        raise
    except Exception:
        # Меню (questionary/prompt_toolkit) требует настоящей консоли — в
        # непривычной среде (перенаправленный вывод, некоторые встроенные
        # терминалы) оно падает с непонятной постороннему пользователю
        # ошибкой. Полный traceback остаётся в логе, а на экране — короткое
        # понятное сообщение.
        logging.getLogger(__name__).exception("Необработанная ошибка")
        print(
            "Что-то пошло не так. Подробности — в data/logs/parser.log.\n"
            "Если это произошло в команде settings — убедитесь, что "
            "программа запущена в обычном окне терминала (не в перенаправленном "
            "выводе и не в ограниченной встроенной консоли)."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
