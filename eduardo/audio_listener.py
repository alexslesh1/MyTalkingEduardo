"""
Цикл прослушивания микрофона и распознавания речи.

Основной путь — офлайн-распознавание через Vosk: быстро, без отправки звука
в облако и без лимитов запросов. Если модель Vosk не установлена в
`models/`, ассистент автоматически переключается на запасной вариант —
Google Web Speech API через библиотеку SpeechRecognition (требует интернет).

В обоих случаях наружу отдаётся один и тот же интерфейс — генератор,
который выдаёт текст команды каждый раз, когда в распознанной речи
встречается слово-триггер "Эдуардо".
"""
from __future__ import annotations

import json
import queue
from collections.abc import Iterator

from . import config


class VoskModelNotFoundError(Exception):
    """Модель Vosk не найдена по указанному пути или библиотеки не установлены."""


def extract_command_after_trigger(text: str) -> str | None:
    """
    Ищет в распознанном тексте слово-триггер и возвращает всё, что сказано
    после него. Возвращает None, если триггер не встретился.
    """
    if not text:
        return None

    text_lower = text.lower()
    best_index = None
    trigger_len = 0

    for trigger in config.TRIGGER_WORDS:
        # rfind, а не find: если в фразе триггер прозвучал несколько раз,
        # интересует команда после последнего упоминания.
        idx = text_lower.rfind(trigger)
        if idx != -1 and (best_index is None or idx > best_index):
            best_index = idx
            trigger_len = len(trigger)

    if best_index is None:
        return None

    command = text[best_index + trigger_len :].strip(" ,.!?")
    return command or None


def listen_with_vosk() -> Iterator[str]:
    """Генератор команд, распознанных через офлайн-модель Vosk."""
    try:
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model
    except ImportError as exc:
        raise VoskModelNotFoundError(
            "Библиотеки vosk/sounddevice не установлены. Выполните: "
            "pip install vosk sounddevice"
        ) from exc

    if not config.VOSK_MODEL_PATH.exists():
        raise VoskModelNotFoundError(
            "Модель Vosk не найдена по пути "
            f"'{config.VOSK_MODEL_PATH}'.\n"
            "Скачайте русскую модель (например, vosk-model-small-ru-0.22) со страницы "
            "https://alphacephei.com/vosk/models, распакуйте архив и поместите папку по "
            f"этому пути (или укажите свой путь через переменную окружения VOSK_MODEL_PATH)."
        )

    model = Model(str(config.VOSK_MODEL_PATH))
    recognizer = KaldiRecognizer(model, config.VOSK_SAMPLE_RATE)

    audio_queue: "queue.Queue[bytes]" = queue.Queue()

    def _audio_callback(indata, frames, time_info, status) -> None:  # noqa: ANN001 - сигнатура sounddevice
        audio_queue.put(bytes(indata))

    with sd.RawInputStream(
        samplerate=config.VOSK_SAMPLE_RATE,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=_audio_callback,
    ):
        print("🎙️  Eduardo слушает (Vosk, офлайн)... Скажите «Эдуардо, <команда>».")
        while True:
            data = audio_queue.get()
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "")
                command = extract_command_after_trigger(text)
                if command:
                    yield command


def listen_with_google_fallback() -> Iterator[str]:
    """Генератор команд, распознанных через Google Web Speech API (запасной вариант, нужен интернет)."""
    try:
        import speech_recognition as sr
    except ImportError as exc:
        raise RuntimeError(
            "Библиотека SpeechRecognition не установлена. Выполните: "
            "pip install SpeechRecognition pyaudio"
        ) from exc

    recognizer = sr.Recognizer()
    microphone = sr.Microphone()

    print(
        "⚠️  Модель Vosk не найдена — использую запасной онлайн-режим (Google Web Speech API).\n"
        "🎙️  Eduardo слушает... Скажите «Эдуардо, <команда>»."
    )

    with microphone as source:
        recognizer.adjust_for_ambient_noise(source)

    while True:
        with microphone as source:
            audio = recognizer.listen(source, phrase_time_limit=10)

        try:
            text = recognizer.recognize_google(audio, language="ru-RU")
        except sr.UnknownValueError:
            continue  # речь не распознана — просто ждём дальше
        except sr.RequestError as exc:
            print(f"[Eduardo] Ошибка запроса к Google Web Speech API (нужен интернет): {exc}")
            continue

        command = extract_command_after_trigger(text)
        if command:
            yield command


def listen_for_commands() -> Iterator[str]:
    """
    Единая точка входа для главного цикла: пытается использовать Vosk,
    при отсутствии модели/библиотек автоматически переключается на
    Google Web Speech API.
    """
    try:
        yield from listen_with_vosk()
    except VoskModelNotFoundError as exc:
        print(f"[Eduardo] {exc}")
        yield from listen_with_google_fallback()
