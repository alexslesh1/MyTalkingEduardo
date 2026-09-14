"""Тесты для actions.py — subprocess (open/osascript) полностью замокан."""
import subprocess
from unittest.mock import patch

import pytest

from eduardo import actions


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestOpenApplication:
    def test_success(self):
        with patch("eduardo.actions.subprocess.run", return_value=_completed(0)) as mock_run:
            result = actions.open_application("Safari")

        assert result["success"] is True
        assert "Safari" in result["message"]
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["open", "-a", "Safari"]

    def test_app_not_found(self):
        with patch(
            "eduardo.actions.subprocess.run",
            return_value=_completed(1, stderr="Unable to find application named"),
        ):
            result = actions.open_application("НесуществующееПриложение")

        assert result["success"] is False
        assert "не удалось" in result["error"].lower()

    def test_empty_name(self):
        result = actions.open_application("   ")
        assert result["success"] is False

    def test_not_macos(self):
        with patch("eduardo.actions.subprocess.run", side_effect=FileNotFoundError):
            result = actions.open_application("Safari")
        assert result["success"] is False
        assert "не macos" in result["error"].lower()

    def test_timeout(self):
        with patch("eduardo.actions.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="open", timeout=10)):
            result = actions.open_application("Safari")
        assert result["success"] is False


class TestWebSearch:
    def test_success(self):
        with patch("eduardo.actions.subprocess.run", return_value=_completed(0)) as mock_run:
            result = actions.web_search("погода в Москве")

        assert result["success"] is True
        assert "google.com/search" in result["url"]
        called_args = mock_run.call_args[0][0]
        assert called_args[0] == "open"
        assert called_args[1] == result["url"]

    def test_empty_query(self):
        result = actions.web_search("   ")
        assert result["success"] is False

    def test_open_failure(self):
        with patch("eduardo.actions.subprocess.run", return_value=_completed(1, stderr="boom")):
            result = actions.web_search("test")
        assert result["success"] is False


class TestOpenTerminalAndCd:
    def test_directory_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        result = actions.open_terminal_and_cd("no_such_dir")
        assert result["success"] is False
        assert "не найдена" in result["error"]

    def test_success_relative_to_documents(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "Documents" / "projects").mkdir(parents=True)

        with patch("eduardo.actions.subprocess.run", return_value=_completed(0)) as mock_run:
            result = actions.open_terminal_and_cd("projects")

        assert result["success"] is True
        script_arg = mock_run.call_args[0][0][2]
        assert "cd " in script_arg
        assert "do script" in script_arg

    def test_tilde_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "custom").mkdir()

        with patch("eduardo.actions.subprocess.run", return_value=_completed(0)):
            result = actions.open_terminal_and_cd("~/custom")

        assert result["success"] is True

    def test_empty_directory(self):
        result = actions.open_terminal_and_cd("")
        assert result["success"] is False

    def test_injection_attempt_is_safe(self, tmp_path, monkeypatch):
        """Спецсимволы в названии папки не должны приводить к исключению или инъекции."""
        monkeypatch.setenv("HOME", str(tmp_path))
        malicious = 'projects"; rm -rf ~ #'

        # Такой папки не существует -> ожидаем аккуратную ошибку, а не падение.
        result = actions.open_terminal_and_cd(malicious)
        assert result["success"] is False
        assert "не найдена" in result["error"]

    def test_osascript_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "Documents" / "projects").mkdir(parents=True)

        with patch("eduardo.actions.subprocess.run", side_effect=FileNotFoundError):
            result = actions.open_terminal_and_cd("projects")

        assert result["success"] is False
        assert "не macos" in result["error"].lower()

    def test_permission_denied_mentions_automation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "Documents" / "projects").mkdir(parents=True)

        with patch(
            "eduardo.actions.subprocess.run",
            return_value=_completed(1, stderr="Not authorized to send Apple events"),
        ):
            result = actions.open_terminal_and_cd("projects")

        assert result["success"] is False
        assert "автоматизация" in result["error"].lower()


class TestStopAssistant:
    def test_stop(self):
        result = actions.stop_assistant()
        assert result["success"] is True
        assert result["stop"] is True
