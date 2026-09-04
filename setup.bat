@echo off
rem Пересоздаёт виртуальное окружение на текущей машине.
rem Сам .venv не переносится копированием папки проекта (внутри него абсолютные
rem пути и платформозависимые бинарники) — поэтому запускайте этот скрипт
rem на каждой новой машине один раз перед первым использованием.

cd /d "%~dp0"

python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

rem Браузер для TikTok-адаптера (Playwright) — ставим внутрь папки проекта,
rem а не в системный кэш пользователя, иначе портативность сломается.
set PLAYWRIGHT_BROWSERS_PATH=%~dp0.playwright-browsers
python -m playwright install chromium

echo.
echo Готово. Дальше запускайте: .venv\Scripts\python.exe main.py
rem pause — иначе при запуске двойным щелчком из проводника окно закроется
rem мгновенно и это сообщение никто не успеет прочитать.
pause
