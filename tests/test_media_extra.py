"""Artwork, seeking and volume, without a player."""

from __future__ import annotations

from typing import Any

from leond import media


class FakeEndpoint:
    def __init__(self, value: float = 0.64) -> None:
        self.value = value
        self.written: list[float] = []

    def GetMasterVolumeLevelScalar(self) -> float:
        return self.value

    def SetMasterVolumeLevelScalar(self, level: float, _context: object) -> None:
        self.written.append(level)
        self.value = level


def test_volume_is_read_as_a_percentage(monkeypatch: Any) -> None:
    monkeypatch.setattr(media, "_endpoint", lambda: FakeEndpoint(0.64))
    assert media.volume() == 64


def test_volume_without_the_audio_bindings_says_so(monkeypatch: Any) -> None:
    monkeypatch.setattr(media, "_endpoint", lambda: None)
    assert media.volume() == -1
    refused = media.set_volume(50)
    assert refused["ok"] is False
    assert "pycaw" in refused["error"]


def test_setting_the_volume_clamps_and_reports(monkeypatch: Any) -> None:
    endpoint = FakeEndpoint()
    monkeypatch.setattr(media, "_endpoint", lambda: endpoint)
    assert media.set_volume(140) == {"ok": True, "volume": 100}
    assert media.set_volume(-5) == {"ok": True, "volume": 0}
    assert endpoint.written == [1.0, 0.0]


def test_an_unreadable_device_is_minus_one(monkeypatch: Any) -> None:
    class Angry:
        def GetMasterVolumeLevelScalar(self) -> float:
            raise OSError("device gone")

    monkeypatch.setattr(media, "_endpoint", lambda: Angry())
    assert media.volume() == -1


def test_the_island_question_needs_no_volume(monkeypatch: Any) -> None:
    monkeypatch.setattr(media, "available", lambda: False)
    answer = media.now()
    assert answer["ok"] is False
    assert answer["playing"] is False
    assert answer["lyrics"]["index"] == -1


def test_state_carries_the_volume_and_a_hint(monkeypatch: Any) -> None:
    monkeypatch.setattr(media, "available", lambda: False)
    state = media.state()
    assert state["ok"] is False
    assert state["volume"] == -1
    assert "pycaw" in state["volume_hint"]


def test_art_without_bindings_explains_itself(monkeypatch: Any) -> None:
    monkeypatch.setattr(media, "available", lambda: False)
    assert media.art()["ok"] is False


def test_seeking_past_the_start_never_reports_a_negative_position(monkeypatch: Any) -> None:
    monkeypatch.setattr(media, "available", lambda: True)
    seen: list[float] = []

    def fake_seek(seconds: float) -> bool:
        seen.append(seconds)
        return True

    monkeypatch.setattr(media, "_seek", fake_seek)

    def fake_run(make: Any, timeout: float) -> bool:
        make()  # the factory is what the real call would have awaited
        return True

    monkeypatch.setattr(media, "_run", fake_run)

    moved = media.seek(-12.5)
    assert moved["ok"] is True
    assert moved["position"] == 0.0
    assert seen == [0.0]
