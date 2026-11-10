"""A launch of the dock, as far as it can run without a desktop.

The window is faked: `create_window` captures exactly what the real call would
receive, and `resize`/`move` record what the page's `set_open` asks Python to
do. That covers the part of `leon` this Linux machine can check — the native
WebView2 window itself only exists on Windows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import webview

from leond import dock
from leond.config import Config


class FakeScreen:
    width = 1366
    height = 768


class FakeWindow:
    def __init__(self) -> None:
        self.size = (0, 0)
        self.pos = (0, 0)
        self.scripts: list[str] = []
        self.minimised = False
        self.destroyed = False

    def resize(self, width: int, height: int) -> None:
        self.size = (width, height)

    def move(self, x: int, y: int) -> None:
        self.pos = (x, y)

    def evaluate_js(self, script: str) -> None:
        self.scripts.append(script)

    def minimize(self) -> None:
        self.minimised = True

    def destroy(self) -> None:
        self.destroyed = True


class SilentAudit:
    """The audit log, without touching the user's %APPDATA% during tests."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: list[tuple[str, str, str]] = []

    def write(self, kind: str, detail: str, outcome: str) -> None:
        self.entries.append((kind, detail, outcome))


def _launch(monkeypatch: Any) -> tuple[FakeWindow, dict[str, Any], Any]:
    window = FakeWindow()
    created: dict[str, Any] = {}

    def fake_create_window(title: str, url: str, **kwargs: Any) -> FakeWindow:
        created.update(kwargs)
        created["title"] = title
        created["url"] = url
        return window

    monkeypatch.setattr(webview, "screens", [FakeScreen()])
    monkeypatch.setattr(webview, "create_window", fake_create_window)
    monkeypatch.setattr(webview, "start", lambda **kwargs: created.update(start=kwargs))
    monkeypatch.setattr(dock, "AuditLog", SilentAudit)

    assert dock.run(Config()) == 0
    return window, created, created["js_api"]


def test_launch_opens_the_capsule_at_the_top_of_the_screen(monkeypatch: Any) -> None:
    window, created, _ = _launch(monkeypatch)
    assert created["title"] == "LEON"
    assert str(created["url"]).endswith("index.html")
    assert (created["width"], created["height"]) == (223, 43)
    assert (created["x"], created["y"]) == ((1366 - 223) // 2, 0)
    assert created["frameless"] is True
    assert created["on_top"] is True
    assert created["transparent"] is True
    assert created["resizable"] is False
    assert created["start"] == {"debug": False}


def test_clicking_the_dock_resizes_the_window_to_the_open_panel(monkeypatch: Any) -> None:
    window, _, api = _launch(monkeypatch)
    api.set_open(True)
    assert window.size == (470, 170)
    assert window.pos == ((1366 - 470) // 2, 0)
    api.set_open(False)
    assert window.size == (223, 43)
    assert window.pos == ((1366 - 223) // 2, 0)


def test_the_bridge_the_page_calls_is_the_one_python_exposes(monkeypatch: Any) -> None:
    _, _, api = _launch(monkeypatch)
    for name in ("hello", "send", "stop", "answer", "set_open", "tools", "open_tool", "act_tool"):
        assert callable(getattr(api, name)), name
    assert api.hello()["model"] == Config().model
    assert [item["id"] for item in api.tools()]


def test_the_window_is_told_about_a_pending_approval(monkeypatch: Any) -> None:
    window, _, api = _launch(monkeypatch)
    api._emit("ask", {"id": "1"})  # noqa: SLF001 - this is the page channel itself
    assert any("window.leon.ask" in script for script in window.scripts)
