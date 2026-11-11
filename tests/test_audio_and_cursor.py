"""The waveform's numbers, and the pointer that the faces follow."""

from __future__ import annotations

import math
import struct
import time
from typing import Any

from leond import audio, cursor


def tone(samples: int, amplitude: int = 9000, rate: int = 44100) -> bytes:
    return b"".join(
        struct.pack("<h", int(amplitude * math.sin(2 * math.pi * 220 * i / rate)))
        for i in range(samples)
    )


def test_silence_is_zero() -> None:
    assert audio.level_from(b"\x00\x00" * 1024) == 0.0
    assert audio.level_from(b"") == 0.0


def test_a_loud_tone_reads_high_and_a_quiet_one_reads_low() -> None:
    loud = audio.level_from(tone(2048))
    quiet = audio.level_from(tone(2048, amplitude=300))
    assert 0.7 <= loud <= 1.0
    assert 0.0 < quiet < loud


def test_an_odd_number_of_bytes_does_not_break_the_meter() -> None:
    assert audio.level_from(tone(64) + b"\x01") > 0.0


def test_a_decayed_level_falls_to_zero() -> None:
    audio._publish(1.0)  # noqa: SLF001 - the clock has to be moved by hand
    assert audio.level() > 0.5
    audio._level = 1.0  # noqa: SLF001
    audio._stamp = time.perf_counter() - 5.0  # noqa: SLF001
    assert audio.level() == 0.0


def test_the_hint_names_the_package_when_it_is_missing(monkeypatch: Any) -> None:
    monkeypatch.setattr(audio, "available", lambda: False)
    assert "pyaudiowpatch" in audio.hint()


def test_stopping_without_starting_is_harmless() -> None:
    audio.stop()
    assert audio.level() == 0.0


def test_the_pointer_is_readable_or_absent() -> None:
    found = cursor.position()
    if found is not None:
        x, y, width, height = found
        assert width >= 0 and height >= 0
        assert isinstance(x, int) and isinstance(y, int)
    else:  # pragma: no cover - only off Windows
        assert cursor.relative((0, 0)) is None


def test_the_relative_pointer_is_offset_by_the_window(monkeypatch: Any) -> None:
    monkeypatch.setattr(cursor, "position", lambda: (700, 40, 1366, 768))
    assert cursor.relative((600, 0)) == {"x": 100, "y": 40}
