"""Global hotkeys for LEON, registered with the Windows message loop.

The hotkeys work while another window has focus. Registration and the message
loop run on their own thread, because RegisterHotKey posts WM_HOTKEY to the
thread that registered it.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
from collections.abc import Callable
from dataclasses import dataclass

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_WIN = 0x0008
VK_C = 0x43
VK_D = 0x44
VK_G = 0x47
VK_J = 0x4A
VK_K = 0x4B
VK_L = 0x4C
VK_N = 0x4E
VK_P = 0x50
VK_R = 0x52
VK_T = 0x54
VK_V = 0x56
VK_SPACE = 0x20
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


@dataclass(frozen=True, slots=True)
class Binding:
    """One global shortcut and what it does."""

    name: str
    mods: int
    vk: int
    action: Callable[[], None]


class Hotkeys:
    """Runs a set of shortcuts on a daemon thread and calls their actions."""

    def __init__(self, bindings: list[Binding]) -> None:
        self._bindings = {index: binding for index, binding in enumerate(bindings, start=1)}
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self.registered: dict[str, bool] = {}

    def start(self) -> dict[str, bool]:
        """Start listening. Maps each name to whether Windows accepted it."""
        self._thread = threading.Thread(target=self._loop, name="leon-hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return dict(self.registered)

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
        for hotkey_id, binding in self._bindings.items():
            ok = bool(user32.RegisterHotKey(None, hotkey_id, binding.mods, binding.vk))
            self.registered[binding.name] = ok
        self._ready.set()
        if not any(self.registered.values()):
            return
        msg = wt.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    pressed = self._bindings.get(int(msg.wParam))
                    if pressed is not None:
                        pressed.action()
        finally:
            for hotkey_id in self._bindings:
                user32.UnregisterHotKey(None, hotkey_id)
