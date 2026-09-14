"""
Реальные действия, которые ассистент выполняет на macOS.

Важно с точки зрения безопасности: наружу (в function calling DeepSeek)
никогда не выставляется функция "выполнить произвольную shell-команду".
Доступны только эти пять фиксированных, заранее проверенных действий —
поэтому голосовое подтверждение "Ты уверен?" для них не требуется.

Каждая функция возвращает словарь вида {"success": bool, ...}, который
затем уходит обратно в DeepSeek как результат вызова функции — модель
формулирует по нему финальный голосовой ответ пользователю.
"""
from __future__ import annotations

import shlex
import subprocess
import urllib.parse
from pathlib import Path

from . import config


def open_application(app_name: str) -> dict:
    """Открыть приложение через `open -a <app_name>`."""
    if not app_name or not app_name.strip():
        return {"success": False, "error": "Не указано имя приложения."}

    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        # Команда `open` есть только на macOS.
        return {"success": False, "error": "Команда `open` недоступна: похоже, это не macOS."}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Превышено время ожидания при открытии «{app_name}»."}

    if result.returncode != 0:
        # macOS возвращает ненулевой код и текст вида
        # "Unable to find application named ...", если приложение не найдено.
        stderr = result.stderr.strip() or "приложение не найдено"
        return {"success": False, "error": f"Не удалось открыть «{app_name}»: {stderr}"}

    return {"success": True, "message": f"Приложение «{app_name}» открыто."}


def web_search(query: str) -> dict:
    """Открыть поиск Google в браузере по умолчанию (новая вкладка в уже открытом окне)."""
    if not query or not query.strip():
        return {"success": False, "error": "Не указан поисковый запрос."}

    query = query.strip()
    url = "https://www.google.com/search?q=" + urllib.parse.quote(query)

    try:
        # Список аргументов (без shell=True) — url передаётся как один
        # аргумент, инъекция через него невозможна.
        result = subprocess.run(["open", url], capture_output=True, text=True, timeout=10)
    except FileNotFoundError:
        return {"success": False, "error": "Команда `open` недоступна: похоже, это не macOS."}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Превышено время ожидания при открытии браузера."}

    if result.returncode != 0:
        return {"success": False, "error": f"Не удалось открыть браузер: {result.stderr.strip()}"}

    return {"success": True, "message": f"Ищу в интернете: «{query}».", "url": url}


def _resolve_documents_path(directory: str) -> Path:
    """
    Разворачивает произнесённый пользователем путь в реальный путь на диске.

    Если путь начинается с "~" или "/" — считаем его самостоятельным
    абсолютным путём, иначе ищем папку внутри ~/Documents (как просили
    в исходной команде "которая в Documents").
    """
    directory = directory.strip()
    if directory.startswith("~") or directory.startswith("/"):
        return Path(directory).expanduser()
    return Path.home() / "Documents" / directory


def open_terminal_and_cd(directory: str) -> dict:
    """
    Открыть Terminal.app и выполнить `cd` в указанную директорию через
    AppleScript (osascript).

    Путь проверяется на существование ДО открытия Terminal, а сама команда
    экранируется на двух уровнях: `shlex.quote` — для shell внутри Terminal,
    и отдельная замена кавычек — для строкового литерала самого AppleScript
    (`do script "..."`). Это исключает shell/AppleScript-инъекции, даже если
    в названии папки окажутся спецсимволы.
    """
    if not directory or not directory.strip():
        return {"success": False, "error": "Не указана директория."}

    target = _resolve_documents_path(directory)

    if not target.exists() or not target.is_dir():
        return {
            "success": False,
            "error": f"Директория «{target}» не найдена. Проверьте название папки.",
        }

    shell_cmd = f"cd {shlex.quote(str(target))}"
    applescript_safe_cmd = shell_cmd.replace("\\", "\\\\").replace('"', '\\"')

    script = (
        f'tell application "{config.TERMINAL_APP_NAME}"\n'
        f"  activate\n"
        f'  do script "{applescript_safe_cmd}"\n'
        f"end tell"
    )

    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    except FileNotFoundError:
        return {"success": False, "error": "Команда `osascript` недоступна: похоже, это не macOS."}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Превышено время ожидания при открытии Terminal."}

    if result.returncode != 0:
        return {
            "success": False,
            "error": (
                f"Не удалось открыть Terminal: {result.stderr.strip()}. "
                "Проверьте разрешение в Системных настройках → Конфиденциальность и "
                "безопасность → Автоматизация → доступ к Terminal."
            ),
        }

    return {"success": True, "message": f"Terminal открыт, перешёл в «{target}»."}


def stop_assistant() -> dict:
    """Сигнал на завершение работы ассистента (реально обрабатывается в главном цикле)."""
    return {"success": True, "message": "Останавливаю работу.", "stop": True}
