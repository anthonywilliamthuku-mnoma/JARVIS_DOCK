"""The dock: one frameless window with LEON inside it.

The window is a WebView2 surface rendering ``leond/ui``. Python owns the model
call, so the page never sees a token, a key or a socket: it can only call the
four methods exposed below. Every finished turn is written to the audit log.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from pathlib import Path
from typing import Any

import webview

from leond import __version__
from leond.audit import AuditLog
from leond.brain import Brain, BrainError, Message, trim
from leond.config import Config, config_dir

UI_DIR = Path(__file__).parent / "ui"
FLUSH_S = 0.05


def _js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


class DockApi:
    """Methods reachable from the page as ``window.pywebview.api.*``."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._brain = Brain(cfg)
        self._audit = AuditLog(config_dir() / "audit.jsonl")
        self._history: list[Message] = []
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._window: webview.Window | None = None
        self._lock = threading.Lock()

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
        self._audit.write("chat", "user pressed stop", "cancelled")
        return {"ok": True}

    def close(self) -> None:
        if self._window is not None:
            self._window.destroy()

    def minimise(self) -> None:
        if self._window is not None:
            self._window.minimize()

    # -- the turn itself -----------------------------------------------------

    def _emit(self, function: str, payload: object) -> None:
        window = self._window
        if window is None:
            return
        # The window can vanish mid-turn; a lost update must never kill the worker.
        with contextlib.suppress(Exception):
            window.evaluate_js(f"window.leon && window.leon.{function}({_js(payload)})")

    def _answer(self, message: str) -> None:
        self._history.append(Message("user", message))
        trimmed = trim(self._history, self._cfg.context)
        started = time.perf_counter()
        first: float | None = None
        pieces: list[str] = []
        pending: list[str] = []
        last_flush = 0.0
        try:
            self._emit("busy", True)
            for delta in self._brain.stream(trimmed, cancel=self._cancel):
                if first is None:
                    first = time.perf_counter()
                pieces.append(delta)
                pending.append(delta)
                now = time.perf_counter()
                if now - last_flush >= FLUSH_S:
                    self._emit("delta", "".join(pending))
                    pending.clear()
                    last_flush = now
            if pending:
                self._emit("delta", "".join(pending))

            reply = "".join(pieces).strip()
            if self._cancel.is_set():
                if reply:
                    self._history.append(Message("assistant", reply))
                self._audit.write("chat", f"{len(reply)} chars", "stopped")
                self._emit("done", {"cancelled": True, "text": reply, "stats": None})
                return
            if not reply:
                self._audit.write("chat", "empty reply", "empty")
                self._emit("error", "the model returned an empty reply")
                return

            self._history.append(Message("assistant", reply))
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
            self._audit.write("chat", f"{type(exc).__name__}", "error")
            self._emit("error", f"unexpected problem: {type(exc).__name__}")
        finally:
            self._emit("busy", False)


def run(cfg: Config) -> int:
    """Open the dock and block until it closes."""
    api = DockApi(cfg)
    window = webview.create_window(
        "LEON",
        str(UI_DIR / "index.html"),
        js_api=api,
        width=cfg.width,
        height=cfg.height,
        min_size=(360, 460),
        frameless=True,
        easy_drag=True,
        on_top=cfg.on_top,
        background_color="#0B0B10",
        resizable=True,
    )
    if window is None:
        raise RuntimeError("the dock window could not be created")
    api.attach(window)
    webview.start(debug=False)
    return 0
