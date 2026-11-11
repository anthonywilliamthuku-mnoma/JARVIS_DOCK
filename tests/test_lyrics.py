"""Lyrics: parsing, matching a line to a second, and the file store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from leond import lyrics, media, tools


def test_timestamps_are_parsed_and_sorted() -> None:
    text = "[00:09.00]later\n[00:01.50]first\n"
    assert [line.text for line in lyrics.parse(text)] == ["first", "later"]
    assert [line.at for line in lyrics.parse(text)] == [1.5, 9.0]


def test_a_line_can_carry_several_timestamps() -> None:
    lines = lyrics.parse("[00:03.00][00:09.00]chorus")
    assert [(line.at, line.text) for line in lines] == [(3.0, "chorus"), (9.0, "chorus")]


def test_whole_second_stamps_and_metadata_lines() -> None:
    text = "[ar:Someone]\n[ti:A song]\n[offset:+200]\n[01:05]a line\n"
    lines = lyrics.parse(text)
    assert len(lines) == 1
    assert lines[0].at == 65.0
    assert lines[0].text == "a line"


def test_untimed_text_is_ignored() -> None:
    assert lyrics.parse("no stamps here\n\n[also not one]") == ()


def test_the_line_at_a_moment_is_the_last_one_to_have_started() -> None:
    lines = lyrics.parse("[00:01.00]a\n[00:03.00]b\n[00:05.00]c")
    assert lyrics.index_at(lines, 0.0) == -1
    assert lyrics.index_at(lines, 1.0) == 0
    assert lyrics.index_at(lines, 2.9) == 0
    assert lyrics.index_at(lines, 3.0) == 1
    assert lyrics.index_at(lines, 99.0) == 2


def test_empty_lyrics_have_no_current_line() -> None:
    assert lyrics.index_at((), 12.0) == -1


def test_a_track_name_is_a_safe_windows_file_name() -> None:
    assert lyrics.name("AC/DC", "Back: in Black?") == "AC_DC - Back_ in Black.lrc"
    assert lyrics.name("", "") == "track.lrc"
    assert "\\" not in lyrics.name("a\\b", "c*d")


def test_saving_and_loading_round_trips(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    target, saved = lyrics.save("Tame Impala", "Let It Happen", "[00:10.00]it's always been\n")
    assert target.parent == tmp_path / "LEON" / "lyrics"
    assert [line.text for line in saved] == ["it's always been"]
    assert lyrics.load("Tame Impala", "Let It Happen") == saved


def test_a_track_without_lyrics_returns_nothing(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert lyrics.load("Nobody", "Nothing") == ()


def test_the_media_tile_is_in_the_registry() -> None:
    assert "media" in {tool.id for tool in tools.TOOLS}


def test_media_control_explains_a_missing_package(monkeypatch: Any) -> None:
    monkeypatch.setattr(media, "available", lambda: False)
    result = tools.act("media", "state")
    assert result["ok"] is False
    assert "winrt-windows-media-control" in result["error"]


def test_saving_lyrics_without_timestamps_is_refused(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(media, "available", lambda: True)
    monkeypatch.setattr(media, "volume", lambda: -1)

    def fake_run(make: Any, timeout: float) -> dict[str, Any]:
        return {
            "title": "Let It Happen",
            "artist": "Tame Impala",
            "album": "Currents",
            "playing": True,
            "position": 12.0,
            "duration": 467.0,
        }

    monkeypatch.setattr(media, "_run", fake_run)
    refused = media.save_lyrics("just the words, no stamps")
    assert refused["ok"] is False
    assert "[00:12.34]" in refused["error"]

    saved = media.save_lyrics("[00:12.00]it's always been\n[00:16.50]a friend of mine\n")
    assert saved["ok"] is True
    assert saved["saved"] == 2
    assert (tmp_path / "LEON" / "lyrics" / "Tame Impala - Let It Happen.lrc").is_file()


def test_the_current_line_follows_the_playhead(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    lyrics.save("A", "B", "[00:01.00]one\n[00:05.00]two\n")

    def fake_run(make: Any, timeout: float) -> dict[str, Any]:
        return {
            "title": "B",
            "artist": "A",
            "album": "",
            "playing": True,
            "position": 6.4,
            "duration": 30.0,
        }

    monkeypatch.setattr(media, "available", lambda: True)
    monkeypatch.setattr(media, "volume", lambda: -1)
    monkeypatch.setattr(media, "_run", fake_run)
    state = media.state()
    assert state["lyrics"]["index"] == 1
    assert state["lyrics"]["count"] == 2
    assert media.lines()["lines"] == ["one", "two"]
