"""Тесты для weather.py — сетевые запросы (requests.get) полностью замокан."""
from unittest.mock import MagicMock, patch

import requests

from eduardo import weather


def _mock_response(status_code=200, json_data=None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data or {}
    return mock


class TestGetWeather:
    def test_success(self):
        json_data = {
            "current_condition": [
                {
                    "temp_C": "15",
                    "FeelsLikeC": "13",
                    "humidity": "60",
                    "weatherDesc": [{"value": "Partly cloudy"}],
                }
            ]
        }
        with patch("eduardo.weather.requests.get", return_value=_mock_response(200, json_data)):
            result = weather.get_weather("Москва")

        assert result["success"] is True
        assert result["city"] == "Москва"
        assert result["temperature_c"] == "15"
        assert result["feels_like_c"] == "13"
        assert result["description"] == "Partly cloudy"
        assert result["humidity"] == "60"

    def test_empty_city(self):
        result = weather.get_weather("")
        assert result["success"] is False
        assert "город" in result["error"].lower()

    def test_connection_error(self):
        with patch("eduardo.weather.requests.get", side_effect=requests.exceptions.ConnectionError):
            result = weather.get_weather("Москва")

        assert result["success"] is False
        assert "интернет" in result["error"].lower()

    def test_timeout(self):
        with patch("eduardo.weather.requests.get", side_effect=requests.exceptions.Timeout):
            result = weather.get_weather("Москва")

        assert result["success"] is False
        assert "не ответил" in result["error"].lower()

    def test_generic_request_exception(self):
        with patch(
            "eduardo.weather.requests.get",
            side_effect=requests.exceptions.RequestException("boom"),
        ):
            result = weather.get_weather("Москва")

        assert result["success"] is False

    def test_bad_status_code(self):
        with patch("eduardo.weather.requests.get", return_value=_mock_response(500)):
            result = weather.get_weather("Москва")

        assert result["success"] is False
        assert "500" in result["error"]

    def test_unrecognized_city(self):
        with patch(
            "eduardo.weather.requests.get",
            return_value=_mock_response(200, {"current_condition": []}),
        ):
            result = weather.get_weather("НесуществующийГородXYZ")

        assert result["success"] is False
        assert "не удалось распознать" in result["error"].lower()

    def test_malformed_json(self):
        mock_response = _mock_response(200)
        mock_response.json.side_effect = ValueError("invalid json")
        with patch("eduardo.weather.requests.get", return_value=mock_response):
            result = weather.get_weather("Москва")

        assert result["success"] is False
