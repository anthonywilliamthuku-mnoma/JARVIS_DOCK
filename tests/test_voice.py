"""Voice commands: the parts that run without a microphone or a model."""

from __future__ import annotations

import struct
import subprocess
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


def test_speak_passes_the_reply_through_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_popen(args: list[str], env: dict[str, str], **kwargs: object) -> None:
        seen["env"] = env
        seen["args"] = args

    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    voice.speak("Hello\n  there '; calc")
    env = seen["env"]
    assert isinstance(env, dict)
    assert env["LEON_SPEAK"] == "Hello there '; calc"
    assert "calc" not in str(seen["args"])


def test_speak_ignores_empty_text(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[object] = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: called.append(a))
    voice.speak("   ")
    assert called == []


def test_speak_with_api_key_does_not_use_the_builtin_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[object] = []
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: called.append(a))
    voice.speak("hello there")
    assert called == []


def test_speak_without_api_key_uses_the_builtin_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[object] = []
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: called.append(a))
    voice.speak("hello there")
    assert len(called) == 1
