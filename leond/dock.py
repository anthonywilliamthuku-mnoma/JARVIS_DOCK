"""The dock: a small island pinned to the top of the screen.

Collapsed it is a pill that shows what LEON is doing; opening it grows the same
window downwards into the conversation. Python owns the model call and every
skill, so the page can only call the handful of methods exposed below.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import threading
import time
from pathlib import Path
from typing import Any

import webview

from leond import __version__, tools
from leond.agent import Agent, Hooks
from leond.audit import AuditLog
from leond.brain import Brain, BrainError, Message
from leond.config import Config, config_dir

UI_DIR = Path(__file__).parent / "ui"

# The dock itself: a 223 x 43 glass capsule at the top of the screen, sized to
# match the reference shell. Opening it grows the same window downwards into a
# 470 x 170 panel, which is the whole budget the tiles and the chat get.
WIDTH = 223
COLLAPSED_H = 43
EXPANDED_W = 470
EXPANDED_H = 170
TOP_MARGIN = 0
FLUSH_S = 0.05
APPROVAL_TIMEOUT_S = 120.0


def geometry(screen_width: int, opened: bool) -> tuple[int, int, int, int]:
    """Where the dock sits for a given screen: (x, y, width, height).

    Collapsed it is exactly ``WIDTH`` x ``COLLAPSED_H``, centred on the screen
    and flush with the top edge, so it reads as a notch. Opening it keeps the
    same centre line and top edge and only grows downwards.
    """
    width = EXPANDED_W if opened else WIDTH
    height = EXPANDED_H if opened else COLLAPSED_H
    width = max(1, min(width, screen_width))
    return max(0, (screen_width - width) // 2), TOP_MARGIN, width, height


def _js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


class DockApi:
    """Methods reachable from the page as ``window.pywebview.api.*``."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._brain = Brain(cfg)
        self._audit = AuditLog(config_dir() / "audit.jsonl")
        self._agent = Agent(cfg, self._brain, self._audit)
        self._history: list[Message] = []
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._window: webview.Window | None = None
        self._lock = threading.Lock()
        self._open = False
        self._tickets = itertools.count(1)
        self._waiting: dict[str, threading.Event] = {}
        self._answers: dict[str, bool] = {}

    def attach(self, window: webview.Window) -> None:
        self._window = window

    # -- called from the page -------------------------------------------------

    def hello(self) -> dict[str, Any]:
        return {
            "version": __version__,
            "model": self._cfg.model,
            "endpoint": self._cfg.endpoint,
            "accent": self._cfg.accent,
        }

    def send(self, text: str) -> dict[str, Any]:
        message = text.strip()
        if not message:
            return {"ok": False, "error": "nothing to send"}
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return {"ok": False, "error": "LEON is still answering"}
            self._cancel.clear()
            self._worker = threading.Thread(
                target=self._answer, args=(message,), name="leon-brain", daemon=True
            )
            self._worker.start()
        self._audit.write("chat", f"{len(message)} chars", "sent")
        return {"ok": True}

    def stop(self) -> dict[str, Any]:
        self._cancel.set()
        for token, event in list(self._waiting.items()):
            self._answers[token] = False
            event.set()
        self._audit.write("chat", "user pressed stop", "cancelled")
        return {"ok": True}

    def answer(self, ticket: str, allowed: bool) -> dict[str, Any]:
        """The user pressed Allow or Deny on the approval card."""
        self._answers[str(ticket)] = bool(allowed)
        event = self._waiting.get(str(ticket))
        if event is not None:
            event.set()
        self._audit.write("approval", str(ticket), "allowed" if allowed else "denied")
        return {"ok": True}

    def set_open(self, opened: bool) -> dict[str, Any]:
        self._resize(bool(opened))
        return {"ok": True}

    # -- tool tiles ----------------------------------------------------------

    def tools(self) -> list[dict[str, Any]]:
        """The grid: every tile with its name, glyph, size and badge."""
        return tools.snapshot()

    def open_tool(self, name: str) -> dict[str, Any]:
        """The opening payload for a tile the user clicked."""
        payload = tools.state(str(name))
        self._audit.write("tool", f"open {name}", "ok" if payload.get("ok") else "refused")
        return payload

    def act_tool(self, name: str, action: str, arg: str = "") -> dict[str, Any]:
        """Run one tile action. The audit log records the call, never its text."""
        result = tools.act(str(name), str(action), str(arg))
        self._audit.write("tool", f"{name}.{action}", "ok" if result.get("ok") else "refused")
        return result

    def minimise(self) -> None:
        if self._window is not None:
            self._window.minimize()

    def close(self) -> None:
        if self._window is not None:
            self._window.destroy()

    # -- window --------------------------------------------------------------

    def _resize(self, opened: bool) -> None:
        if self._window is None:
            return
        self._open = opened
        with contextlib.suppress(Exception):
            screen = webview.screens[0] if webview.screens else None
            x, y, width, height = geometry(getattr(screen, "width", 1920), opened)
            self._window.resize(width, height)
            self._window.move(x, y)

    # -- the turn ------------------------------------------------------------

    def _emit(self, function: str, payload: object) -> None:
        window = self._window
        if window is None:
            return
        with contextlib.suppress(Exception):
            window.evaluate_js(f"window.leon && window.leon.{function}({_js(payload)})")

    def _ask(self, name: str, detail: str, reason: str) -> bool:
        ticket = str(next(self._tickets))
        event = threading.Event()
        self._waiting[ticket] = event
        self._answers[ticket] = False
        self._resize(True)
        self._emit("ask", {"id": ticket, "name": name, "detail": detail, "reason": reason})
        answered = event.wait(APPROVAL_TIMEOUT_S)
        approved = self._answers.pop(ticket, False)
        self._waiting.pop(ticket, None)
        self._emit("askClosed", ticket)
        if not answered:
            self._audit.write("approval", name, "timed out")
        return approved

    def _answer(self, message: str) -> None:
        started = time.perf_counter()
        first: float | None = None
        pending: list[str] = []
        last_flush = 0.0

        def on_text(piece: str) -> None:
            nonlocal first, last_flush
            if first is None:
                first = time.perf_counter()
            pending.append(piece)
            now = time.perf_counter()
            if now - last_flush >= FLUSH_S:
                self._emit("delta", "".join(pending))
                pending.clear()
                last_flush = now

        hooks = Hooks(
            on_text=on_text,
            on_state=lambda text: self._emit("state", text),
            ask=self._ask,
        )

        try:
            self._emit("busy", True)
            reply = self._agent.answer(self._history, message, hooks, self._cancel)
            if pending:
                self._emit("delta", "".join(pending))
            if self._cancel.is_set():
                self._audit.write("chat", f"{len(reply)} chars", "stopped")
                self._emit("done", {"cancelled": True, "text": reply, "stats": None})
                return
            if not reply:
                self._audit.write("chat", "empty reply", "empty")
                self._emit("error", "the model returned an empty reply")
                return
            elapsed = time.perf_counter() - started
            tokens = max(1, len(reply) // 4)
            stats = {
                "seconds": round(elapsed, 1),
                "first_ms": int((first - started) * 1000) if first is not None else None,
                "tokens": tokens,
                "per_second": round(tokens / elapsed, 1) if elapsed > 0 else 0.0,
            }
            self._audit.write("chat", f"{tokens} tokens", "ok")
            self._emit("done", {"cancelled": False, "text": reply, "stats": stats})
        except BrainError as exc:
            self._audit.write("chat", str(exc)[:120], "error")
            self._emit("error", str(exc))
        except Exception as exc:  # noqa: BLE001 - the UI must always be told
            self._audit.write("chat", type(exc).__name__, "error")
            self._emit("error", f"unexpected problem: {type(exc).__name__}")
        finally:
            self._emit("busy", False)


def run(cfg: Config) -> int:
    """Open the island and block until it closes."""
    api = DockApi(cfg)
    screen = webview.screens[0] if webview.screens else None
    x, y, width, height = geometry(getattr(screen, "width", 1920), opened=False)
    window = webview.create_window(
        "LEON",
        str(UI_DIR / "index.html"),
        js_api=api,
        width=width,
        height=height,
        x=x,
        y=y,
        frameless=True,
        easy_drag=True,
        on_top=True,
        transparent=True,
        background_color="#000000",
        resizable=False,
    )
    if window is None:
        raise RuntimeError("the dock window could not be created")
    api.attach(window)
    print(
        f"LEON dock: {width}x{height} at {x},{y} "
        f"on a {getattr(screen, 'width', 0)}x{getattr(screen, 'height', 0)} screen",
        flush=True,
    )
    webview.start(debug=False)
    return 0
