"""Seeing the screen, and touching it when the user said so.

Three separate things, because they carry very different risk:

* ``foreground_title`` and ``capture`` are read-only, and ``capture`` writes a
  screenshot into LEON's own folder so the OCR pass has a file to read.
* ``text`` turns that screenshot into words with the OCR engine that ships in
  Windows, so a model that cannot see images still gets something to reason
  about.
* ``type_text`` and ``click`` drive the focused window. They exist because LEON
  should be able to help with what is on screen, but they are only ever reached
  through a policy check and an Allow card, never from a tool tile click alone.

Everything is plain ``ctypes`` against user32/gdi32, so there is no new runtime
to install, and every function answers with a sentence the UI can show instead
of raising.
"""

from __future__ import annotations

import ctypes
import json
import struct
import subprocess
import time
from array import array
from datetime import datetime
from pathlib import Path
from typing import Any

from leond import winrt
from leond.config import config_dir

HINT = (
    "Reading the screen's text needs Windows OCR. Run `uv add "
    "winrt-windows-media-ocr winrt-windows-graphics-imaging winrt-windows-storage "
    "winrt-windows-storage-streams` and reopen the dock."
)
MAX_TEXT = 6000
MAX_TYPED = 400

_SRCCOPY = 0x00CC0020
_CBM_CREATE = 0x40000000
_BI_RGB = 0
_DIB_RGB_COLORS = 0

_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004
_INPUT_KEYBOARD = 1
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [("bmiHeader", _BitmapInfoHeader), ("bmiColors", ctypes.c_uint32 * 3)]


class _KeyInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_uint16),
        ("wScan", ctypes.c_uint16),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_uint32),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_uint32),
        ("wParamL", ctypes.c_uint16),
        ("wParamH", ctypes.c_uint16),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("ki", _KeyInput), ("mi", _MouseInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_uint32), ("u", _InputUnion)]


_prepared = False


def _libs() -> tuple[Any, Any] | None:
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return None
    return getattr(windll, "user32", None), getattr(windll, "gdi32", None)


def _prepare() -> tuple[Any, Any] | None:
    """Declare the handle-returning calls, so 64-bit pointers are not cut."""
    global _prepared
    libs = _libs()
    if libs is None:
        return None
    user32, gdi32 = libs
    if _prepared:
        return libs
    pointer = ctypes.c_void_p
    gdi32.CreateCompatibleDC.argtypes = [pointer]
    gdi32.CreateCompatibleDC.restype = pointer
    gdi32.CreateCompatibleBitmap.argtypes = [pointer, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = pointer
    gdi32.SelectObject.argtypes = [pointer, pointer]
    gdi32.SelectObject.restype = pointer
    gdi32.BitBlt.argtypes = [
        pointer,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        pointer,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint32,
    ]
    gdi32.BitBlt.restype = ctypes.c_int
    gdi32.GetDIBits.argtypes = [
        pointer,
        pointer,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.POINTER(_BitmapInfo),
        ctypes.c_uint,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [pointer]
    gdi32.DeleteDC.argtypes = [pointer]
    user32.GetDC.argtypes = [pointer]
    user32.GetDC.restype = pointer
    user32.ReleaseDC.argtypes = [pointer, pointer]
    _prepared = True
    return libs


def _screens_folder() -> Path:
    return config_dir() / "screens"


def _write_bmp(target: Path, pixels: bytes, width: int, height: int) -> None:
    size = len(pixels)
    file_header = struct.pack("<2sIHHI", b"BM", 14 + 40 + size, 0, 0, 14 + 40)
    info_header = struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, _BI_RGB, size, 0, 0, 0, 0)
    target.write_bytes(file_header + info_header + pixels)


def capture(target: Path | None = None) -> dict[str, Any]:
    """Copy the primary screen to a BMP in LEON's folder."""
    libs = _prepare()
    if libs is None:
        return {"ok": False, "error": "looking at the screen needs Windows"}
    user32, gdi32 = libs
    width = int(user32.GetSystemMetrics(0))
    height = int(user32.GetSystemMetrics(1))
    if width <= 0 or height <= 0:
        return {"ok": False, "error": "the screen size was not reported"}

    screen = user32.GetDC(None)
    if not screen:
        return {"ok": False, "error": "the screen could not be opened"}
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    try:
        if not memory or not bitmap:
            return {"ok": False, "error": "the screen could not be copied"}
        gdi32.SelectObject(memory, bitmap)
        copied = gdi32.BitBlt(memory, 0, 0, width, height, screen, 0, 0, _SRCCOPY | _CBM_CREATE)
        if not copied:
            return {"ok": False, "error": "the screen could not be copied"}

        info = _BitmapInfo()
        info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = _BI_RGB
        buffer = ctypes.create_string_buffer(width * height * 4)
        rows = gdi32.GetDIBits(
            memory, bitmap, 0, height, buffer, ctypes.byref(info), _DIB_RGB_COLORS
        )
        if rows != height:
            return {"ok": False, "error": "the screen's pixels could not be read"}

        path = target or _screens_folder() / f"screen-{datetime.now():%Y%m%d-%H%M%S}.bmp"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_bmp(path, buffer.raw, width, height)
        except OSError as exc:
            return {"ok": False, "error": f"the screenshot could not be saved: {exc}"}
        return {"ok": True, "path": str(path), "width": width, "height": height}
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory:
            gdi32.DeleteDC(memory)
        user32.ReleaseDC(None, screen)


def _run(make: Any, timeout: float) -> Any:
    """Await one WinRT call on the apartment thread that owns it."""
    return winrt.run_async(make, timeout)


async def _ocr(path: Path) -> str:
    storage_file = winrt.klass("windows.storage", "StorageFile")
    access = winrt.klass("windows.storage", "FileAccessMode")
    decoder = winrt.klass("windows.graphics.imaging", "BitmapDecoder")
    engine_class = winrt.klass("windows.media.ocr", "OcrEngine")
    if storage_file is None or access is None or decoder is None or engine_class is None:
        raise RuntimeError("the OCR namespaces are missing")

    file = await storage_file.get_file_from_path_async(str(path))
    if file is None:
        raise RuntimeError("the screenshot could not be opened")
    stream = await file.open_async(access.READ)
    codec = await decoder.create_async(stream)
    bitmap = await codec.get_software_bitmap_async()
    engine = engine_class.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError("no OCR language is installed for this user")
    result = await engine.recognize_async(bitmap)
    return str(result.text)


# UI Automation, through the .NET assemblies that ship with Windows. This is
# what actually works from an unpackaged desktop app: Windows.Media.Ocr needs
# MSIX package identity and answers "Class not registered" without it.
_UIA_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class LeonFront {
  [DllImport("user32.dll")]
  public static extern IntPtr GetForegroundWindow();
}
"@
$hwnd = [LeonFront]::GetForegroundWindow()
if ($hwnd -eq [IntPtr]::Zero) { '{"ok":false,"error":"no window is in front"}'; exit }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$names = New-Object System.Collections.Generic.List[string]
function LeonWalk($element, $depth) {
  if ($depth -gt 7 -or $names.Count -ge 220) { return }
  $name = $element.Current.Name
  if ($name -and $name.Trim().Length -gt 0) { $names.Add($name.Trim()) }
  $child = $walker.GetFirstChild($element)
  while ($null -ne $child) { LeonWalk $child ($depth + 1); $child = $walker.GetNextSibling($child) }
}
LeonWalk $root 0
$unique = $names | Select-Object -Unique
$out = @{
  ok = $true
  title = $root.Current.Name
  count = @($unique).Count
  text = ($unique -join ' | ')
}
$out | ConvertTo-Json -Compress
"""


def _uia() -> dict[str, Any]:
    """Read the front window's controls and their labels."""
    try:
        completed = subprocess.run(  # noqa: S603 - a fixed script, not model text
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "-",
            ],
            input=_UIA_SCRIPT,
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": f"the screen reader did not run: {type(exc).__name__}"}
    line = next(
        (raw for raw in reversed(completed.stdout.splitlines()) if raw.strip().startswith("{")),
        "",
    )
    if not line:
        return {"ok": False, "error": "the screen reader returned nothing"}
    try:
        found = json.loads(line)
    except json.JSONDecodeError:
        return {"ok": False, "error": "the screen reader returned something unreadable"}
    return found if isinstance(found, dict) else {"ok": False, "error": "unexpected shape"}


def _ocr_text() -> dict[str, Any]:
    """The pixels' words, where Windows OCR is available at all."""
    if winrt.klass("windows.media.ocr", "OcrEngine") is None:
        return {"ok": False, "error": HINT}
    shot = capture()
    if not shot.get("ok"):
        return shot
    try:
        shot_path = Path(str(shot["path"]))
        found = _run(lambda: _ocr(shot_path), 20.0)
    except Exception as exc:  # noqa: BLE001 - OCR fails in several documented ways
        reason = str(exc).strip() or type(exc).__name__
        return {"ok": False, "error": f"OCR: {reason}"}
    return {"ok": True, "text": " ".join(found.split()), "path": shot["path"]}


def text() -> dict[str, Any]:
    """What is on screen, read the most reliable way this PC allows.

    The front window's own controls come first: they carry the real words and
    which window they belong to. Where that yields nothing - a canvas, a video,
    a browser that does not expose its page - the pixels are tried, and at
    worst the screen is saved as a picture and said so.
    """
    window = foreground_title()
    found = _uia()
    body = " ".join(str(found.get("text") or "").split())
    if found.get("ok") and body:
        return {
            "ok": True,
            "text": body[:MAX_TEXT],
            "source": "uia",
            "window": window or str(found.get("title") or ""),
            "count": int(found.get("count") or 0),
        }

    pixels = _ocr_text()
    words = " ".join(str(pixels.get("text") or "").split())
    if pixels.get("ok") and words:
        return {
            "ok": True,
            "text": words[:MAX_TEXT],
            "source": "ocr",
            "window": window,
            "count": 0,
        }

    shot = capture()
    if not shot.get("ok"):
        return {"ok": False, "error": str(shot.get("error") or "the screen could not be read")}
    return {
        "ok": True,
        "text": "",
        "source": "screenshot",
        "window": window,
        "count": 0,
        "path": shot["path"],
        "message": (
            "nothing readable was exposed by the front window; "
            f"the screen is saved at {shot['path']}"
        ),
    }


def foreground_title() -> str:
    """The title of the window in front, or an empty string."""
    libs = _libs()
    if libs is None:
        return ""
    user32, _ = libs
    handle = user32.GetForegroundWindow()
    if not handle:
        return ""
    length = int(user32.GetWindowTextLengthW(handle))
    buffer = ctypes.create_unicode_buffer(length + 2)
    user32.GetWindowTextW(handle, buffer, length + 1)
    return buffer.value.strip()[:120]


def type_text(value: str) -> dict[str, Any]:
    """Type into whatever window has focus, as if on the keyboard."""
    libs = _libs()
    if libs is None:
        return {"ok": False, "error": "typing needs Windows"}
    user32, _ = libs
    body = value[:MAX_TYPED]
    if not body:
        return {"ok": False, "error": "there was nothing to type"}

    units = array("H", body.encode("utf-16-le"))
    sent = 0
    for unit in units:
        for flag in (0, _KEYEVENTF_KEYUP):
            event = _Input(
                type=_INPUT_KEYBOARD,
                u=_InputUnion(
                    ki=_KeyInput(wVk=0, wScan=unit, dwFlags=_KEYEVENTF_UNICODE | flag, time=0)
                ),
            )
            if not user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(_Input)):
                return {"ok": False, "error": "Windows refused the keystrokes"}
            sent += 1
    time.sleep(0.02)
    return {"ok": True, "typed": len(body), "keystrokes": sent}


def click(x: int, y: int) -> dict[str, Any]:
    """Left-click once at a screen position."""
    libs = _libs()
    if libs is None:
        return {"ok": False, "error": "clicking needs Windows"}
    user32, _ = libs
    if not user32.SetCursorPos(int(x), int(y)):
        return {"ok": False, "error": "the pointer could not be moved"}
    user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.03)
    user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    return {"ok": True, "x": int(x), "y": int(y)}
