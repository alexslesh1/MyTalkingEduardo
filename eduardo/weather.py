"""Получение текущей погоды через бесплатный сервис wttr.in (без ключа API)."""
from __future__ import annotations

import urllib.parse

import requests

from . import config


def get_weather(city: str) -> dict:
    """
    Возвращает реальные данные о погоде для города через wttr.in.

    DeepSeek сам погоду не знает — эта функция получает настоящие цифры,
    а модель на втором шаге только формулирует по ним ответ на русском.
    """
    if not city or not city.strip():
        return {"success": False, "error": "Не указан город."}

    city = city.strip()
    encoded_city = urllib.parse.quote(city)
    # format=j1 — полный JSON-ответ wttr.in с текущими условиями.
    url = f"{config.WTTR_BASE_URL}/{encoded_city}?format=j1"

    try:
        response = requests.get(url, timeout=config.HTTP_TIMEOUT)
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Нет подключения к интернету — не удалось узнать погоду."}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Сервис погоды не ответил вовремя."}
    except requests.exceptions.RequestException as exc:
        return {"success": False, "error": f"Ошибка при запросе погоды: {exc}"}

    if response.status_code != 200:
        return {"success": False, "error": f"Сервис погоды вернул ошибку (код {response.status_code})."}

    try:
        data = response.json()
        current = data["current_condition"][0]
        temp_c = current["temp_C"]
        feels_like_c = current["FeelsLikeC"]
        description = current["weatherDesc"][0]["value"]
        humidity = current["humidity"]
    except (ValueError, KeyError, IndexError):
        # wttr.in почти всегда отвечает 200, даже если не смог распознать
        # город — просто данные внутри будут пустыми/некорректными.
        return {"success": False, "error": f"Не удалось распознать город «{city}»."}

    return {
        "success": True,
        "city": city,
        "temperature_c": temp_c,
        "feels_like_c": feels_like_c,
        "description": description,
        "humidity": humidity,
    }
