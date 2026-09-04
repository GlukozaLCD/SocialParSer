#!/usr/bin/env bash
# Пересоздаёт виртуальное окружение на текущей машине.
# Сам .venv не переносится копированием папки проекта (внутри него абсолютные
# пути и платформозависимые бинарники) — поэтому запускайте этот скрипт
# на каждой новой машине один раз перед первым использованием.
set -e

cd "$(dirname "$0")"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

# Браузер для TikTok-адаптера (Playwright) — ставим внутрь папки проекта,
# а не в системный кэш пользователя, иначе портативность сломается.
export PLAYWRIGHT_BROWSERS_PATH="$(pwd)/.playwright-browsers"
python -m playwright install chromium

echo
echo "Готово. Дальше запускайте: .venv/bin/python main.py"
