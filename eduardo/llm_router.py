"""
Роутинг голосовых команд через DeepSeek API (function calling).

Логика в два шага:

1. `route_command()` отправляет текст команды в DeepSeek вместе с описанием
   доступных функций (`TOOLS`) — модель решает, какую функцию вызвать и с
   какими аргументами. Сама модель никакого действия не выполняет.
2. Python реально выполняет действие (см. actions.py / weather.py), и
   `generate_final_reply()` отправляет результат этого действия обратно в
   DeepSeek, чтобы модель сформулировала естественный ответ на русском —
   он озвучивается через `say`. Так модель никогда не "выдумывает" данные
   вроде погоды — она только пересказывает то, что реально пришло из API.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from openai import APIConnectionError, APIError, OpenAI

from . import config

SYSTEM_PROMPT = (
    "Ты — голосовой ассистент Eduardo для macOS. Пользователь произносит команды "
    "по-русски после слова-триггера «Эдуардо». Твоя задача — понять намерение "
    "пользователя и вызвать ровно одну подходящую функцию с правильными аргументами. "
    "Если ни одна функция не подходит, ничего не вызывай, а просто вежливо ответь "
    "текстом, что не понял команду. "
    "Когда тебе передают результат выполнения функции — отвечай кратко и естественно "
    "по-русски, одним-двумя предложениями, как будто ты голосом сообщаешь результат "
    "пользователю. Никогда не выдумывай данные (например, погоду) — используй только "
    "то, что реально пришло в результате функции. Если в результате success=false — "
    "извинись и кратко объясни причину из поля error."
)

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Открыть указанное приложение на macOS (аналог `open -a <app>`).",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Имя приложения, например 'Safari', 'Заметки', 'Calculator'.",
                    }
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Узнать текущую погоду в указанном городе.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "Название города, например 'Москва' или 'Berlin'.",
                    }
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Найти информацию в интернете и открыть результаты поиска Google в браузере.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_terminal_cd",
            "description": "Открыть Terminal.app и перейти в указанную папку внутри ~/Documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Имя папки внутри Documents, например 'projects' или 'projects/myapp'.",
                    }
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_assistant",
            "description": "Полностью завершить работу голосового ассистента Eduardo.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


@dataclass
class RoutedCommand:
    """Результат первого шага: какую функцию (если есть) вызвать и с какими аргументами."""

    function_name: str | None
    arguments: dict[str, Any] = field(default_factory=dict)
    assistant_message: dict[str, Any] | None = None  # нужно для истории диалога на втором шаге
    tool_call_id: str | None = None
    direct_reply: str | None = None  # если модель не вызвала функцию, а сразу ответила текстом


class LLMRouterError(Exception):
    """Ошибка общения с DeepSeek API: нет интернета, неверный ключ, пустой ответ и т.п."""


def _get_client() -> OpenAI:
    if not config.DEEPSEEK_API_KEY:
        raise LLMRouterError(
            "Не задан DEEPSEEK_API_KEY. Установите переменную окружения с ключом DeepSeek "
            "(export DEEPSEEK_API_KEY=sk-...)."
        )
    return OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL)


def route_command(command_text: str) -> RoutedCommand:
    """Отправляет команду пользователя в DeepSeek и получает выбранную функцию с аргументами."""
    client = _get_client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": command_text},
    ]

    try:
        response = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
    except APIConnectionError as exc:
        raise LLMRouterError("Нет подключения к DeepSeek API — проверьте интернет.") from exc
    except APIError as exc:
        raise LLMRouterError(f"DeepSeek API вернул ошибку: {exc}") from exc

    if not response.choices:
        raise LLMRouterError("DeepSeek вернул пустой ответ.")

    message = response.choices[0].message
    tool_calls = getattr(message, "tool_calls", None)

    if not tool_calls:
        # Модель не выбрала функцию — например, команда ей непонятна.
        content = (message.content or "").strip()
        return RoutedCommand(
            function_name=None,
            direct_reply=content or "Извините, я не понял команду.",
        )

    tool_call = tool_calls[0]
    try:
        arguments = json.loads(tool_call.function.arguments or "{}")
    except json.JSONDecodeError:
        arguments = {}

    # Сохраняем сообщение ассистента в формате, пригодном для истории диалога —
    # он понадобится на втором шаге (generate_final_reply), чтобы DeepSeek
    # видел контекст своего же вызова функции.
    assistant_message = {
        "role": "assistant",
        "content": message.content,
        "tool_calls": [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
        ],
    }

    return RoutedCommand(
        function_name=tool_call.function.name,
        arguments=arguments,
        assistant_message=assistant_message,
        tool_call_id=tool_call.id,
    )


def generate_final_reply(command_text: str, routed: RoutedCommand, function_result: dict[str, Any]) -> str:
    """
    Второй шаг: передаём DeepSeek реальный результат выполненного действия,
    чтобы модель сформулировала финальный голосовой ответ пользователю.
    """
    client = _get_client()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": command_text},
        routed.assistant_message,
        {
            "role": "tool",
            "tool_call_id": routed.tool_call_id,
            "content": json.dumps(function_result, ensure_ascii=False),
        },
    ]

    try:
        response = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=messages,
        )
    except APIConnectionError as exc:
        raise LLMRouterError("Нет подключения к DeepSeek API — проверьте интернет.") from exc
    except APIError as exc:
        raise LLMRouterError(f"DeepSeek API вернул ошибку: {exc}") from exc

    if not response.choices:
        raise LLMRouterError("DeepSeek вернул пустой ответ.")

    content = (response.choices[0].message.content or "").strip()
    if not content:
        # Если модель ничего не ответила — подстрахуемся сообщением из самого результата.
        content = function_result.get("message") or function_result.get("error") or "Готово."

    return content
