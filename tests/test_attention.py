"""Asking for attention: pause, ping, glow, wait, put it back."""

from __future__ import annotations

import time
from typing import Any

from leond import attention


class Recorder:
    """Stands in for the page, the speakers and the media session."""

    def __init__(self, playing: bool, answered: bool) -> None:
        self.playing = playing
        self.answered = answered
        self.events: list[tuple[str, Any]] = []
        self.toggles = 0
        self.tones: list[tuple[int, int]] = []

    def is_playing(self) -> bool:
        return self.playing

    def pause(self) -> bool:
        self.toggles += 1
        return True

    def emit(self, name: str, payload: object) -> None:
        self.events.append((name, payload))

    def wait(self, _timeout: float) -> bool:
        return self.answered

    def beep(self, frequency: int, duration_ms: int) -> None:
        self.tones.append((frequency, duration_ms))


def test_playing_playback_is_paused_and_then_resumed() -> None:
    recorder = Recorder(playing=True, answered=True)
    ping = attention.ask(
        "your class starts in five minutes",
        is_playing=recorder.is_playing,
        pause=recorder.pause,
        emit=recorder.emit,
        wait=recorder.wait,
        beep=recorder.beep,
        beats=(0, 1, 2),
    )
    assert ping.paused is True
    assert recorder.toggles == 2  # paused, then put back
    assert ping.answered is True
    assert "resumed" in ping.sentence()


def test_the_page_is_told_to_glow_before_the_wait_and_released_after() -> None:
    recorder = Recorder(playing=False, answered=False)
    attention.ask(
        "",
        is_playing=recorder.is_playing,
        pause=recorder.pause,
        emit=recorder.emit,
        wait=recorder.wait,
        beep=recorder.beep,
        beats=(0, 1, 2),
    )
    names = [name for name, _ in recorder.events]
    assert names == ["attention", "attentionDone"]
    payload: dict[str, Any] = dict(recorder.events)["attention"]
    assert payload["reason"] == "may I have a moment?"
    assert payload["beats"] == [0, 1, 2]


def test_nothing_is_paused_when_nothing_is_playing() -> None:
    recorder = Recorder(playing=False, answered=True)
    ping = attention.ask(
        "hello",
        is_playing=recorder.is_playing,
        pause=recorder.pause,
        emit=recorder.emit,
        wait=recorder.wait,
        beep=recorder.beep,
    )
    assert recorder.toggles == 0
    assert ping.paused is False
    assert ping.sentence() == "The user answered the ping."


def test_an_unanswered_ping_still_hands_the_music_back() -> None:
    recorder = Recorder(playing=True, answered=False)
    ping = attention.ask(
        "hey",
        is_playing=recorder.is_playing,
        pause=recorder.pause,
        emit=recorder.emit,
        wait=recorder.wait,
        beep=recorder.beep,
    )
    assert ping.answered is False
    assert recorder.toggles == 2
    assert "resumed anyway" in ping.sentence()


def test_the_tones_follow_the_beats() -> None:
    recorder = Recorder(playing=False, answered=True)
    attention.ask(
        "",
        is_playing=recorder.is_playing,
        pause=recorder.pause,
        emit=recorder.emit,
        wait=recorder.wait,
        beep=recorder.beep,
        beats=(0, 40),
    )
    deadline = time.time() + 1.0
    while len(recorder.tones) < 4 and time.time() < deadline:
        time.sleep(0.02)
    assert recorder.tones[:2] == [(880, 85), (660, 100)]
    assert len(recorder.tones) >= 4


def test_a_missing_media_session_is_not_a_failure() -> None:
    def broken() -> bool:
        raise RuntimeError("no session")

    seen: list[tuple[str, Any]] = []
    ping = attention.ask(
        "hi",
        is_playing=broken,
        pause=lambda: True,
        emit=lambda name, payload: seen.append((name, payload)),
        wait=lambda _t: True,
        beep=lambda _f, _d: None,
    )
    assert ping.ok is True
    assert ping.paused is False
    assert seen[0][0] == "attention"
