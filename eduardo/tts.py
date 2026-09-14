"""Озвучка текста через встроенную команду macOS `say`."""
from __future__ import annotations

import subprocess

from . import config


def speak(text: str, voice: str | None = None) -> None:
    """Произносит текст голосом macOS. На не-macOS системах просто печатает в консоль."""
    if not text or not text.strip():
        return

    voice = voice or config.TTS_VOICE

    try:
        subprocess.run(["say", "-v", voice, text], timeout=30)
    except FileNotFoundError:
        # Например, при разработке/тестах не на macOS.
        print(f"[TTS недоступен, вывод в консоль] {text}")
    except subprocess.TimeoutExpired:
        print("[TTS] Превышено время ожидания озвучки.")
