"""Global hotkeys for LEON, registered with the Windows message loop.

The hotkey works while another window has focus. Registration and the message
loop run on their own thread, because RegisterHotKey posts WM_HOTKEY to the
thread that registered it.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
from collections.abc import Callable

MOD_ALT = 0x0001
MOD_WIN = 0x0008
VK_J = 0x4A
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 1


class Hotkey:
    """Runs a Win + Alt + J listener on a daemon thread and calls ``action``."""

    def __init__(self, action: Callable[[], None]) -> None:
        self._action = action
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self.registered = False

    def start(self) -> bool:
        """Start listening. Returns False if Windows refused the hotkey."""
        self._thread = threading.Thread(target=self._loop, name="leon-hotkey", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self.registered

    def stop(self) -> None:
        """Stop the listener and wait for its thread to exit."""
        if self._thread is None:
            return
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(timeout=2.0)
        self._thread = None

    def _loop(self) -> None:
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        self.registered = bool(user32.RegisterHotKey(None, HOTKEY_ID, MOD_WIN | MOD_ALT, VK_J))
        self._ready.set()
        if not self.registered:
            return
        msg = wt.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    self._action()
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)
