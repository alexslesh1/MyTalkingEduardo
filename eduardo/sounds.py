"""Воспроизведение короткого системного звука при обнаружении слова-триггера."""
from __future__ import annotations

import subprocess

from . import config


def play_wake_sound() -> None:
    """Проигрывает системный звук "проснулся", чтобы пользователь понял, что команда услышана."""
    try:
        subprocess.run(["afplay", config.WAKE_SOUND_PATH], timeout=5)
    except FileNotFoundError:
        pass  # Не macOS — молча пропускаем, это не критично.
    except subprocess.TimeoutExpired:
        pass
