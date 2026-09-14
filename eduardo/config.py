"""Конфигурация ассистента Eduardo: ключи, пути, константы."""
from __future__ import annotations

import os
from pathlib import Path

# --- DeepSeek API ---
# Ключ берём из переменной окружения — никогда не хардкодим в коде.
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# --- Слово-триггер ---
# Разные варианты, которые распознавалка речи может выдать для "Эдуардо"
# (Vosk и Google STT не всегда точны в передаче имён собственных).
TRIGGER_WORDS = ["эдуардо", "едуардо", "эдуарда", "eduardo"]

# --- Распознавание речи (Vosk) ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VOSK_MODEL_PATH = Path(
    os.environ.get("VOSK_MODEL_PATH", str(PROJECT_ROOT / "models" / "vosk-model-small-ru-0.22"))
)
VOSK_SAMPLE_RATE = 16000

# --- Озвучка (TTS) ---
# "Milena" — стандартный русский голос macOS. Можно переопределить через env,
# если у пользователя установлен другой (например, "Yuri").
TTS_VOICE = os.environ.get("EDUARDO_TTS_VOICE", "Milena")

# --- Звук пробуждения ---
WAKE_SOUND_PATH = "/System/Library/Sounds/Pop.aiff"

# --- Погода ---
WTTR_BASE_URL = "https://wttr.in"
HTTP_TIMEOUT = 6  # секунд

# --- Терминал ---
TERMINAL_APP_NAME = "Terminal"
