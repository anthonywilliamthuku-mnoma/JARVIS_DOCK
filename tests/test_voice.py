"""Voice commands: the parts that run without a microphone or a model."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from leond import voice


def _pcm(value: int, count: int = 160) -> bytes:
    return struct.pack(f"<{count}h", *([value] * count))


def test_silence_is_below_the_speech_threshold() -> None:
    assert voice._rms(_pcm(0)) == 0.0


def test_loud_audio_is_above_the_speech_threshold() -> None:
    assert voice._rms(_pcm(8000)) > voice.SPEECH_RMS


def test_listen_reports_a_missing_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(voice, "available", lambda: False)
    result = voice.listen()
    assert result["ok"] is False
    assert "Vosk model" in str(result["error"])
