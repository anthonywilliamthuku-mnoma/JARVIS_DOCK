"""Seeing the screen, and the files left on the dock."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from leond import inbox, screen

# -- the screen's guards ----------------------------------------------------


def test_without_windows_every_screen_call_explains_itself(monkeypatch: Any) -> None:
    monkeypatch.setattr(screen, "_libs", lambda: None)
    monkeypatch.setattr(screen, "_prepare", lambda: None)
    assert screen.capture()["ok"] is False
    assert "Windows" in screen.capture()["error"]
    assert screen.type_text("hello")["ok"] is False
    assert screen.click(10, 10)["ok"] is False
    assert screen.foreground_title() == ""


def test_typing_nothing_is_refused(monkeypatch: Any) -> None:
    class FakeUser32:
        pass

    monkeypatch.setattr(screen, "_libs", lambda: (FakeUser32(), FakeUser32()))
    result = screen.type_text("")
    assert result["ok"] is False
    assert "nothing to type" in result["error"]


def test_a_missing_reader_line_is_reported(monkeypatch: Any) -> None:
    class Finished:
        stdout = "PowerShell says no"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Finished())
    assert screen._uia()["ok"] is False  # noqa: SLF001 - the parser is the subject


def test_the_reader_parses_its_json_line(monkeypatch: Any) -> None:
    class Finished:
        stdout = 'noise\n{"ok":true,"title":"Notepad","count":2,"text":"File | Edit"}'
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Finished())
    found = screen._uia()  # noqa: SLF001
    assert found["text"] == "File | Edit"
    assert found["count"] == 2


def test_the_front_window_wins_over_the_pixels(monkeypatch: Any) -> None:
    monkeypatch.setattr(screen, "foreground_title", lambda: "Notepad")
    monkeypatch.setattr(screen, "_uia", lambda: {"ok": True, "text": "Hello   there", "count": 2})
    readable = screen.text()
    assert readable["source"] == "uia"
    assert readable["text"] == "Hello there"
    assert readable["window"] == "Notepad"


def test_an_empty_front_window_falls_back_to_a_screenshot(monkeypatch: Any) -> None:
    monkeypatch.setattr(screen, "foreground_title", lambda: "Video call")
    monkeypatch.setattr(screen, "_uia", lambda: {"ok": True, "text": "", "count": 0})
    monkeypatch.setattr(screen, "_ocr_text", lambda: {"ok": False, "error": "no OCR"})
    monkeypatch.setattr(
        screen,
        "capture",
        lambda: {"ok": True, "path": "/tmp/shot.bmp", "width": 10, "height": 10},
    )
    found = screen.text()
    assert found["ok"] is True
    assert found["source"] == "screenshot"
    assert found["path"] == "/tmp/shot.bmp"
    assert "saved at" in found["message"]


def test_pixels_are_used_when_they_have_words(monkeypatch: Any) -> None:
    monkeypatch.setattr(screen, "foreground_title", lambda: "Canvas")
    monkeypatch.setattr(screen, "_uia", lambda: {"ok": True, "text": ""})
    monkeypatch.setattr(screen, "_ocr_text", lambda: {"ok": True, "text": "  a b  c "})
    readable = screen.text()
    assert readable["source"] == "ocr"
    assert readable["text"] == "a b c"


# -- held files -------------------------------------------------------------


def test_the_inbox_counts_files_and_names_them(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(inbox, "folder", lambda: tmp_path)
    assert inbox.count() == 0
    assert "not holding any files" in inbox.describe()

    (tmp_path / "lecture-notes.md").write_text("week 3", encoding="utf-8")
    (tmp_path / "voice-memo.wav").write_bytes(b"RIFF")
    (tmp_path / "subfolder").mkdir()

    assert inbox.count() == 2
    sentence = inbox.describe()
    assert "2 file(s)" in sentence
    assert "lecture-notes.md" in sentence


def test_a_missing_inbox_is_simply_empty(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(inbox, "folder", lambda: tmp_path / "not-there")
    assert inbox.listing() == []
    assert inbox.count() == 0
