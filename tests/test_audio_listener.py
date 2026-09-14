"""Тесты для логики извлечения команды из распознанного текста (без реального микрофона)."""
from eduardo.audio_listener import extract_command_after_trigger


class TestExtractCommandAfterTrigger:
    def test_basic_trigger(self):
        assert extract_command_after_trigger("эдуардо открой сафари") == "открой сафари"

    def test_trigger_in_the_middle(self):
        text = "так вот эдуардо какая погода в москве"
        assert extract_command_after_trigger(text) == "какая погода в москве"

    def test_no_trigger_returns_none(self):
        assert extract_command_after_trigger("привет как дела") is None

    def test_empty_text_returns_none(self):
        assert extract_command_after_trigger("") is None

    def test_trigger_without_command_returns_none(self):
        assert extract_command_after_trigger("эдуардо") is None

    def test_alternative_spelling_recognized(self):
        assert extract_command_after_trigger("едуардо стоп") == "стоп"

    def test_uses_last_occurrence(self):
        text = "эдуардо эдуардо найди в интернете котиков"
        assert extract_command_after_trigger(text) == "найди в интернете котиков"

    def test_strips_trailing_punctuation(self):
        assert extract_command_after_trigger("эдуардо, открой заметки.") == "открой заметки"
