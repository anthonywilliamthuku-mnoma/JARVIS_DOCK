import os
from pathlib import Path

import pytest

from leond import tools


def test_every_tile_is_well_formed() -> None:
    ids = [tool.id for tool in tools.TOOLS]
    assert len(ids) == len(set(ids))
    assert {tool.size for tool in tools.TOOLS} <= {"small", "wide", "large"}
    payload = tools.snapshot()
    assert len(payload) == len(tools.TOOLS)
    for item in payload:
        assert {"id", "name", "glyph", "size", "blurb", "badge"} <= set(item)


def test_every_tile_can_report_a_state() -> None:
    for tool in tools.TOOLS:
        payload = tools.state(tool.id)
        assert "ok" in payload, tool.id


def test_unknown_tool_is_refused() -> None:
    assert tools.act("teleport", "go")["ok"] is False
    assert tools.state("teleport")["ok"] is False


# -- calculator ------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("200 + 15", "215"),
        ("20% of 150", "30"),
        ("2^10", "1,024"),  # a whole answer also shows hex and binary
        ("5!", "120"),
        ("sqrt(16)", "4"),
        ("0x1F", "31"),
        ("(3 + 4) * 2", "14"),
    ],
)
def test_calculator_answers(expression: str, expected: str) -> None:
    assert tools.calculate(expression).startswith(expected)


def test_calculator_converts_units() -> None:
    assert tools.calculate("5 km to mi").endswith("mi")
    assert tools.calculate("72 f in c").startswith("22.2")


def test_calculator_refuses_more_than_sums() -> None:
    assert "not a sum" in tools.calculate("1/0")
    assert "do not know" in tools.calculate("secret + 1")
    assert "cannot use" in tools.calculate("price: £5")
    assert "not a sum" in tools.calculate("3 + ")


# -- calendar --------------------------------------------------------------


def test_calendar_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert tools.read_events() == []

    added = tools.add_event("2031-03-04 09:05 Dentist")
    assert added["ok"] is True
    assert tools.read_events() == [("2031-03-04", "09:05", "Dentist")]

    view = tools.month_view("2031-03")
    assert view["label"] == "March 2031"
    assert view["days"] == 31
    assert view["events"]["2031-03-04"] == ["09:05 Dentist"]


def test_calendar_rejects_nonsense(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert tools.add_event("tomorrow please")["ok"] is False
    assert tools.add_event("2031-02-30 10:00 Never")["ok"] is False
    assert tools.add_event("2031-03-04 25:00 Late")["ok"] is False


# -- QR --------------------------------------------------------------------


def test_qr_makes_svg() -> None:
    result = tools.make_qr("https://example.com")
    assert result["ok"] is True
    assert "<svg" in result["svg"]


def test_qr_needs_content() -> None:
    assert tools.make_qr("   ")["ok"] is False


# -- notes -----------------------------------------------------------------


def test_notes_are_listed_and_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    folder = tmp_path / "LEON" / "notes"
    folder.mkdir(parents=True)
    (folder / "shopping.md").write_text("# Shopping\n\nmilk\n", encoding="utf-8")

    listed = tools.note_list()
    assert listed == [{"name": "shopping", "title": "Shopping"}]
    read = tools.note_read("shopping")
    assert read["ok"] is True
    assert "milk" in read["text"]
    assert tools.note_read("missing")["ok"] is False


# -- launching -------------------------------------------------------------


def test_launch_refuses_a_hard_denied_target() -> None:
    result = tools.launch("format d:")
    assert result["ok"] is False
    assert "refused" in result["error"]


def test_launch_reports_unknown_targets() -> None:
    assert tools.launch("C:\\definitely\\not\\here")["ok"] is False
    assert tools.launch("")["ok"] is False


def test_launch_opens_a_url_without_a_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []

    def fake_open(url: str) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr("leond.tools.webbrowser.open", fake_open)
    assert tools.launch("https://example.com")["ok"] is True
    assert opened == ["https://example.com"]


# -- platform-specific tiles ----------------------------------------------


@pytest.mark.skipif(os.name == "nt", reason="POSIX has no clipboard here")
def test_clipboard_says_so_off_windows() -> None:
    assert tools.write_clipboard("hello") is False
    assert tools.grab_clipboard()["ok"] is False


@pytest.mark.skipif(os.name == "nt", reason="keep-awake is a Windows call")
def test_keep_awake_needs_windows() -> None:
    result = tools.act("awake", "on", "15")
    assert result["ok"] is False
    assert "Windows" in result["error"]


def test_timer_is_handled_in_the_page() -> None:
    assert tools.act("timer", "beep")["ok"] is True


def test_optional_tiles_explain_what_is_missing() -> None:
    state = tools.state("voice")
    if state["ok"]:
        pytest.skip("sounddevice is installed here")
    assert "sounddevice" in state["error"]
