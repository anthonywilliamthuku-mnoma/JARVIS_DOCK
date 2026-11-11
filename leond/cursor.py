"""Where the pointer is, in screen pixels.

The faces follow the pointer across the whole desktop, not just while it is
over the dock, so the position has to come from Windows rather than from a
mouse event in the page. The dock turns this into window-local pixels before
sending it on, because the page has no idea where its window sits.
"""

from __future__ import annotations

import ctypes
from typing import Any


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _user32() -> Any:
    windll = getattr(ctypes, "windll", None)
    return getattr(windll, "user32", None) if windll is not None else None


def position() -> tuple[int, int, int, int] | None:
    """(x, y, screen_width, screen_height), or ``None`` off Windows."""
    user32 = _user32()
    if user32 is None:
        return None
    point = _Point()
    if not user32.GetCursorPos(ctypes.byref(point)):
        return None
    width = int(user32.GetSystemMetrics(0))
    height = int(user32.GetSystemMetrics(1))
    if width <= 0 or height <= 0:
        return None
    return int(point.x), int(point.y), width, height


def relative(origin: tuple[int, int]) -> dict[str, int] | None:
    """The pointer in window pixels, for a window whose corner is ``origin``."""
    found = position()
    if found is None:
        return None
    x, y, _, _ = found
    return {"x": x - origin[0], "y": y - origin[1]}
