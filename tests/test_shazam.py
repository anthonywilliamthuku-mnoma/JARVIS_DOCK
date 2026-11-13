from pathlib import Path

import pytest

from leond import mods, shazam


def test_token_cleans_pasted_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDD_API_TOKEN", "  <abc123>\n")
    assert shazam.token() == "abc123"


def test_identify_needs_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUDD_API_TOKEN", raising=False)
    result = shazam.identify(10)
    assert result["ok"] is False
    assert "AUDD_API_TOKEN" in result["error"]


def test_parse_audd_match() -> None:
    payload = {
        "status": "OK",
        "result": {
            "title": "Song",
            "artist": "Artist",
            "album": "Album",
            "release_date": "2020-01-01",
            "apple_music": {"url": "https://music.apple.com/song", "artwork": "https://img"},
        },
    }
    result = shazam._parse(payload)
    assert result["ok"] is True
    assert result["title"] == "Song"
    assert result["url"].startswith("https://")


def test_mods_dir_points_at_leon_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert mods.mods_dir() == tmp_path / "LEON" / "mods"
    assert mods.list_mods() == []
