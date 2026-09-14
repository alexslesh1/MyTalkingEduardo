"""
Точка входа голосового ассистента Eduardo.

Запуск: python -m eduardo
"""
from __future__ import annotations

from typing import Any, Callable

from . import actions, config, llm_router, sounds, tts, weather
from .audio_listener import listen_for_commands
from .llm_router import LLMRouterError, RoutedCommand

# Диспетчер: имя функции (как в TOOLS в llm_router.py) -> реальное действие на Mac.
ACTION_DISPATCH: dict[str, Callable[[dict[str, Any]], dict]] = {
    "open_application": lambda args: actions.open_application(args.get("app_name", "")),
    "get_weather": lambda args: weather.get_weather(args.get("city", "")),
    "web_search": lambda args: actions.web_search(args.get("query", "")),
    "open_terminal_cd": lambda args: actions.open_terminal_and_cd(args.get("directory", "")),
    "stop_assistant": lambda args: actions.stop_assistant(),
}


def handle_command(command_text: str) -> bool:
    """
    Обрабатывает одну голосовую команду целиком: LLM-роутинг → реальное
    действие на Mac → озвучка результата.

    Возвращает True, если ассистент должен остановиться.
    """
    print(f"[Eduardo] Команда: {command_text}")

    try:
        routed: RoutedCommand = llm_router.route_command(command_text)
    except LLMRouterError as exc:
        tts.speak(f"Ошибка связи с сервером: {exc}")
        return False

    if routed.function_name is None:
        # DeepSeek не смог сопоставить команду ни одной функции.
        tts.speak(routed.direct_reply or "Извините, я не понял команду.")
        return False

    action = ACTION_DISPATCH.get(routed.function_name)
    if action is None:
        tts.speak("Внутренняя ошибка: неизвестная функция.")
        return False

    function_result = action(routed.arguments)

    if function_result.get("stop"):
        tts.speak(function_result.get("message", "Останавливаю работу."))
        return True

    try:
        reply_text = llm_router.generate_final_reply(command_text, routed, function_result)
    except LLMRouterError:
        # Даже если DeepSeek недоступен на втором шаге — сообщаем пользователю
        # хоть что-то по данным самой функции, не молчим.
        reply_text = function_result.get("message") or function_result.get("error") or "Готово."

    tts.speak(reply_text)
    return False


def main() -> None:
    print("=" * 60)
    print("Eduardo — голосовой ассистент для macOS")
    print("=" * 60)

    if not config.DEEPSEEK_API_KEY:
        print(
            "⚠️  Переменная окружения DEEPSEEK_API_KEY не задана.\n"
            "    Установите её перед запуском: export DEEPSEEK_API_KEY=sk-..."
        )

    tts.speak("Эдуардо к работе готов.")

    try:
        for command_text in listen_for_commands():
            sounds.play_wake_sound()
            should_stop = handle_command(command_text)
            if should_stop:
                break
    except KeyboardInterrupt:
        print("\n[Eduardo] Остановлен пользователем (Ctrl+C).")
    except RuntimeError as exc:
        print(f"[Eduardo] Критическая ошибка распознавания речи: {exc}")


if __name__ == "__main__":
    main()
