"""
Тесты для llm_router.py — реальные вызовы к DeepSeek не выполняются:
класс OpenAI полностью замокан, ответы API эмулируются через SimpleNamespace.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from openai import APIConnectionError, APIError

from eduardo import config, llm_router
from eduardo.llm_router import LLMRouterError, RoutedCommand


def _make_tool_call(name: str, arguments: dict, call_id: str = "call_1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments, ensure_ascii=False)),
    )


def _make_response(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")


class TestRouteCommand:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")

        with pytest.raises(LLMRouterError):
            llm_router.route_command("какая погода в Москве")

    def test_function_call_parsed_correctly(self):
        tool_call = _make_tool_call("get_weather", {"city": "Москва"})
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_response(tool_calls=[tool_call])

        with patch("eduardo.llm_router.OpenAI", return_value=mock_client):
            routed = llm_router.route_command("какая погода в Москве")

        assert routed.function_name == "get_weather"
        assert routed.arguments == {"city": "Москва"}
        assert routed.tool_call_id == "call_1"
        assert routed.assistant_message is not None

        # Модель вызывалась именно с описанием инструментов (function calling).
        _, kwargs = mock_client.chat.completions.create.call_args
        assert kwargs["tools"] == llm_router.TOOLS
        assert kwargs["model"] == config.DEEPSEEK_MODEL

    def test_open_application_call_parsed(self):
        tool_call = _make_tool_call("open_application", {"app_name": "Safari"})
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_response(tool_calls=[tool_call])

        with patch("eduardo.llm_router.OpenAI", return_value=mock_client):
            routed = llm_router.route_command("открой сафари")

        assert routed.function_name == "open_application"
        assert routed.arguments == {"app_name": "Safari"}

    def test_no_tool_call_returns_direct_reply(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_response(
            content="Не понял, что нужно сделать.", tool_calls=None
        )

        with patch("eduardo.llm_router.OpenAI", return_value=mock_client):
            routed = llm_router.route_command("абракадабра")

        assert routed.function_name is None
        assert routed.direct_reply == "Не понял, что нужно сделать."

    def test_no_tool_call_and_empty_content_has_fallback_reply(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_response(content=None, tool_calls=None)

        with patch("eduardo.llm_router.OpenAI", return_value=mock_client):
            routed = llm_router.route_command("что-то невнятное")

        assert routed.function_name is None
        assert routed.direct_reply == "Извините, я не понял команду."

    def test_malformed_arguments_json_falls_back_to_empty_dict(self):
        tool_call = SimpleNamespace(
            id="call_1",
            function=SimpleNamespace(name="stop_assistant", arguments="not-valid-json"),
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_response(tool_calls=[tool_call])

        with patch("eduardo.llm_router.OpenAI", return_value=mock_client):
            routed = llm_router.route_command("эдуардо стоп")

        assert routed.function_name == "stop_assistant"
        assert routed.arguments == {}

    def test_empty_choices_raises(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(choices=[])

        with patch("eduardo.llm_router.OpenAI", return_value=mock_client):
            with pytest.raises(LLMRouterError):
                llm_router.route_command("что-то")

    def test_connection_error_raises_llm_router_error(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())

        with patch("eduardo.llm_router.OpenAI", return_value=mock_client):
            with pytest.raises(LLMRouterError, match="интернет"):
                llm_router.route_command("что-то")

    def test_api_error_raises_llm_router_error(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APIError(
            "invalid api key", request=MagicMock(), body=None
        )

        with patch("eduardo.llm_router.OpenAI", return_value=mock_client):
            with pytest.raises(LLMRouterError):
                llm_router.route_command("что-то")


class TestGenerateFinalReply:
    def _routed(self):
        return RoutedCommand(
            function_name="get_weather",
            arguments={"city": "Москва"},
            assistant_message={"role": "assistant", "content": None, "tool_calls": []},
            tool_call_id="call_1",
        )

    def test_success(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_response(
            content="В Москве сейчас 15 градусов, облачно."
        )

        with patch("eduardo.llm_router.OpenAI", return_value=mock_client):
            reply = llm_router.generate_final_reply(
                "какая погода в Москве",
                self._routed(),
                {"success": True, "temperature_c": "15", "description": "Cloudy"},
            )

        assert reply == "В Москве сейчас 15 градусов, облачно."

        # Убеждаемся, что реальный результат функции ушёл в модель как tool-сообщение.
        _, kwargs = mock_client.chat.completions.create.call_args
        tool_message = kwargs["messages"][-1]
        assert tool_message["role"] == "tool"
        assert json.loads(tool_message["content"])["temperature_c"] == "15"

    def test_empty_content_falls_back_to_function_result_message(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_response(content="")

        with patch("eduardo.llm_router.OpenAI", return_value=mock_client):
            reply = llm_router.generate_final_reply(
                "открой сафари",
                self._routed(),
                {"success": True, "message": "Приложение «Safari» открыто."},
            )

        assert reply == "Приложение «Safari» открыто."

    def test_empty_content_falls_back_to_error_when_no_message(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_response(content=None)

        with patch("eduardo.llm_router.OpenAI", return_value=mock_client):
            reply = llm_router.generate_final_reply(
                "какая погода в Урюпинске",
                self._routed(),
                {"success": False, "error": "Не удалось распознать город."},
            )

        assert reply == "Не удалось распознать город."

    def test_connection_error_raises(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())

        with patch("eduardo.llm_router.OpenAI", return_value=mock_client):
            with pytest.raises(LLMRouterError):
                llm_router.generate_final_reply("что-то", self._routed(), {"success": True})
