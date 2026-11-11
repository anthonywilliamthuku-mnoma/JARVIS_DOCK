"""The dock's tool tiles: Nook 0.4.2's utilities, rebuilt for LEON.

Nook ships these as Rust modules drawn with egui. LEON cannot reuse that
runtime, so each tile here is a small Python backend behind the same
pywebview bridge the chat uses, and the page draws the grid.

Rules that keep it safe and cheap:

* Read-only tools (system monitor, calculator, QR) never touch the machine.
* Anything that changes the PC (keep-awake, clipboard, calendar, launching)
  goes through :mod:`leond.policy` first, and every call is audited.
* Modules whose Windows API is missing answer with the reason and what to
  install, rather than raising into the UI.
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import re
import subprocess
import threading
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from leond import facts, inbox, media, screen, skills
from leond.config import config_dir
from leond.policy import Tier, check

MAX_TEXT = 4000
CLIP_HISTORY = 30


@dataclass(frozen=True, slots=True)
class Tool:
    """One tile in the dock's grid."""

    id: str
    name: str
    glyph: str
    size: str  # "small" | "wide" | "large"
    blurb: str
    tier: Tier = Tier.OBSERVE


TOOLS: tuple[Tool, ...] = (
    Tool("awake", "Keep awake", "◐", "small", "Stop the screen from sleeping.", Tier.ACT),
    Tool("timer", "Timer", "◷", "small", "Countdown and stopwatch."),
    Tool("calc", "Calculator", "=", "wide", "Sums, percentages and units."),
    Tool("system", "System", "▤", "wide", "CPU, memory and free space."),
    Tool("calendar", "Calendar", "▦", "small", "Today, and the month ahead.", Tier.ACT),
    Tool("qr", "QR code", "▩", "small", "Turn text into a scannable code."),
    Tool("clipboard", "Clipboard", "▣", "small", "What you copied, newest first.", Tier.ACT),
    Tool("notes", "Notes", "✎", "small", "Notes LEON has written.", Tier.ACT),
    Tool("launch", "Quick launch", "▶", "wide", "Apps, folders and settings pages.", Tier.ACT),
    Tool("colour", "Colour picker", "◉", "small", "Copy the colour under the cursor.", Tier.ACT),
    Tool("voice", "Voice memo", "●", "small", "Record the microphone to WAV.", Tier.ACT),
    Tool(
        "screen",
        "Screen",
        "◫",
        "small",
        "What is on screen: the words in the front window, or a picture.",
        Tier.ACT,
    ),
    Tool("media", "Media", "♪", "wide", "Now playing, with synced lyrics."),
)

_INDEX = {tool.id: tool for tool in TOOLS}


def tool_list() -> list[Tool]:
    return list(TOOLS)


# -- keep awake -------------------------------------------------------------

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002

_awake_stop = threading.Event()
_awake_until: float | None = None
_awake_thread: threading.Thread | None = None
_awake_lock = threading.Lock()


def _kernel32() -> Any:
    windll = getattr(ctypes, "windll", None)
    return getattr(windll, "kernel32", None) if windll is not None else None


def _hold_execution(flags: int) -> None:
    kernel32 = _kernel32()
    if kernel32 is not None:
        kernel32.SetThreadExecutionState(ctypes.c_uint(flags))


def _awake_worker(until: float | None, stop: threading.Event) -> None:
    """Hold the display awake on this thread, which must stay alive for it."""
    _hold_execution(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED)
    try:
        while not stop.is_set():
            if until is not None and time.time() >= until:
                break
            stop.wait(5.0)
    finally:
        _hold_execution(_ES_CONTINUOUS)  # release


def _awake_on(minutes: int) -> dict[str, Any]:
    global _awake_until, _awake_thread
    if _kernel32() is None:
        return {"ok": False, "error": "keeping the PC awake needs Windows"}
    with _awake_lock:
        _awake_stop.set()
        if _awake_thread is not None and _awake_thread.is_alive():
            _awake_thread.join(timeout=6)
        _awake_stop.clear()
        _awake_until = None if minutes <= 0 else time.time() + minutes * 60
        _awake_thread = threading.Thread(
            target=_awake_worker,
            args=(_awake_until, _awake_stop),
            name="leon-awake",
            daemon=True,
        )
        _awake_thread.start()
    label = "until switched off" if minutes <= 0 else f"for {minutes} minutes"
    return {"ok": True, "message": f"Keeping the PC awake {label}.", "state": _awake_state()}


def _awake_off() -> dict[str, Any]:
    global _awake_until, _awake_thread
    with _awake_lock:
        _awake_stop.set()
        if _awake_thread is not None and _awake_thread.is_alive():
            _awake_thread.join(timeout=6)
        _awake_thread = None
        _awake_until = None
    return {"ok": True, "message": "The PC may sleep again.", "state": _awake_state()}


def _awake_state() -> dict[str, Any]:
    on = _awake_thread is not None and _awake_thread.is_alive()
    until = ""
    if on and _awake_until is not None:
        until = datetime.fromtimestamp(_awake_until).strftime("%H:%M")
    return {"on": on, "until": until}


# -- system monitor ---------------------------------------------------------


class _FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]

    def value(self) -> int:
        return int((self.high << 32) | self.low)


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_uint32),
        ("memory_load", ctypes.c_uint32),
        ("total_phys", ctypes.c_uint64),
        ("avail_phys", ctypes.c_uint64),
        ("total_page", ctypes.c_uint64),
        ("avail_page", ctypes.c_uint64),
        ("total_virtual", ctypes.c_uint64),
        ("avail_virtual", ctypes.c_uint64),
        ("avail_extended", ctypes.c_uint64),
    ]


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


_cpu_prev: tuple[int, int, int] | None = None
_cpu_lock = threading.Lock()


def _cpu_times() -> tuple[int, int, int] | None:
    kernel32 = _kernel32()
    if kernel32 is None:
        return None
    idle, kernel, user = _FileTime(), _FileTime(), _FileTime()
    if not kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return None
    return idle.value(), kernel.value(), user.value()


def cpu_percent() -> int:
    """Processor load since the previous call, 0-100."""
    global _cpu_prev
    sample = _cpu_times()
    if sample is None:
        return -1
    with _cpu_lock:
        previous, _cpu_prev = _cpu_prev, sample
    if previous is None:
        return 0
    idle = sample[0] - previous[0]
    total = (sample[1] - previous[1]) + (sample[2] - previous[2])
    if total <= 0:
        return 0
    return int(max(0, min(100, round(100 * (total - idle) / total))))


def memory_percent() -> int:
    kernel32 = _kernel32()
    if kernel32 is None:
        return -1
    status = _MemoryStatus()
    status.length = ctypes.sizeof(_MemoryStatus)
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return -1
    return int(status.memory_load)


def _system_state() -> dict[str, Any]:
    free_gb, total_gb = facts.disk_free()
    return {
        "cpu": cpu_percent(),
        "memory": memory_percent(),
        "free_gb": free_gb,
        "disk_total_gb": total_gb,
    }


# -- calculator -------------------------------------------------------------

_ALLOWED_FUNCS: dict[str, Any] = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log10,
    "ln": math.log,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
}
_CONSTANTS = {"pi": math.pi, "e": math.e, "π": math.pi}

_UNITS: dict[tuple[str, str], float] = {
    ("km", "mi"): 0.621371,
    ("mi", "km"): 1.609344,
    ("kg", "lb"): 2.204623,
    ("lb", "kg"): 0.453592,
    ("m", "ft"): 3.280840,
    ("ft", "m"): 0.304800,
    ("cm", "in"): 0.393701,
    ("in", "cm"): 2.540000,
    ("gb", "mb"): 1024.0,
    ("mb", "gb"): 1 / 1024.0,
    ("h", "min"): 60.0,
    ("min", "s"): 60.0,
    ("l", "gal"): 0.264172,
    ("gal", "l"): 3.785412,
}
_TEMPS = {"c": "c", "f": "f", "k": "k"}


def _strip_expression(text: str) -> str:
    cleaned = text.strip().lower().replace("×", "*").replace("÷", "/").replace(",", "")
    return cleaned.replace("^", "**")


def _to_celsius(value: float, unit: str) -> float:
    if unit == "f":
        return (value - 32) * 5 / 9
    if unit == "k":
        return value - 273.15
    return value


def _from_celsius(value: float, unit: str) -> float:
    if unit == "f":
        return value * 9 / 5 + 32
    if unit == "k":
        return value + 273.15
    return value


def _convert(amount: float, source: str, target: str) -> float | None:
    if source in _TEMPS and target in _TEMPS:
        return _from_celsius(_to_celsius(amount, source), target)
    factor = _UNITS.get((source, target))
    return None if factor is None else amount * factor


def calculate(text: str) -> str:
    """Answer an arithmetic expression, or explain why it cannot."""
    raw = text.strip()
    if not raw:
        return ""
    source = _strip_expression(raw)

    percent_of = re.fullmatch(r"([\d.]+)\s*%\s*of\s*([\d.]+)", source)
    if percent_of:
        return _format(float(percent_of.group(1)) / 100 * float(percent_of.group(2)))

    conversion = re.fullmatch(r"([\d.]+)\s*([a-z°]+)\s*(?:to|in)\s*([a-z°]+)", source)
    if conversion:
        source_unit = conversion.group(2).replace("°", "")
        target_unit = conversion.group(3).replace("°", "")
        value = _convert(float(conversion.group(1)), source_unit, target_unit)
        if value is None:
            return "I cannot convert those units yet."
        return f"{_format(value)} {target_unit}"

    expression = source.replace("mod", "%")
    if re.search(r"[^0-9a-zA-Z_+\-*/%(). !π]", expression):
        return "That has characters a calculator cannot use."
    if len(expression) > 120:
        return "That expression is too long."

    factorial = re.fullmatch(r"(\d{1,3})!", expression)
    if factorial:
        return str(math.factorial(int(factorial.group(1))))

    try:
        value = _evaluate(expression)
    except (ValueError, SyntaxError, TypeError, ZeroDivisionError, OverflowError):
        return "That is not a sum I can solve."
    except NameError:
        return "I do not know that name."

    if isinstance(value, bool):
        return "That is not a sum I can solve."
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "That does not have a finite answer."
    return _format(value, expression)


def _format(value: float, expression: str = "") -> str:
    if float(value).is_integer() and abs(value) < 1e15:
        number = f"{int(value):,}"
    else:
        number = f"{value:,.6g}"
    if expression:
        extra: list[str] = []
        try:
            whole = int(value)
        except (ValueError, OverflowError):
            whole = 0
        if abs(value - whole) < 1e-9 and abs(whole) > 255:
            extra.append(f"0x{whole:X}")
            extra.append(f"0b{whole:b}")
        if extra:
            return f"{number}  ({' · '.join(extra)})"
    return number


def _evaluate(expression: str) -> float:
    import ast

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp):
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise ZeroDivisionError
                return left / right
            if isinstance(node.op, ast.Pow):
                if abs(right) > 128:
                    raise OverflowError
                return float(left**right)
            if isinstance(node.op, ast.Mod):
                return math.fmod(left, right)
            raise ValueError("operator")
        if isinstance(node, ast.UnaryOp):
            value = walk(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.Name):
            if node.id in _CONSTANTS:
                return float(_CONSTANTS[node.id])
            raise NameError(node.id)
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("call")
            function = _ALLOWED_FUNCS.get(node.func.id)
            if function is None:
                raise NameError(node.func.id)
            return float(function(*[walk(arg) for arg in node.args]))
        raise ValueError("expression")

    return walk(ast.parse(expression, mode="eval"))


# -- QR codes ---------------------------------------------------------------


def make_qr(text: str) -> dict[str, Any]:
    body = text.strip()[:MAX_TEXT]
    if not body:
        return {"ok": False, "error": "type something to encode"}
    try:
        import segno  # noqa: PLC0415 - optional, only needed for this tile
    except ImportError:
        return {"ok": False, "error": "QR codes need `uv add segno`"}
    code = segno.make(body, error="m")
    return {"ok": True, "svg": code.svg_inline(scale=4, border=1, dark="#101018")}


# -- calendar ---------------------------------------------------------------

_EVENT = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})\s+(.+)$")


def calendar_path() -> Path:
    return config_dir() / "calendar.txt"


def read_events() -> list[tuple[str, str, str]]:
    """Every saved event as (date, time, text)."""
    path = calendar_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        return []
    events: list[tuple[str, str, str]] = []
    for line in lines:
        match = _EVENT.match(line.strip())
        if match:
            date, hour, minute, text = match.groups()
            events.append((date, f"{int(hour):02d}:{minute}", text))
    return events


def add_event(raw: str) -> dict[str, Any]:
    match = _EVENT.match(raw.strip())
    if not match:
        return {"ok": False, "error": "use `2026-11-10 20:30 Dentist`"}
    date, hour, minute, text = match.groups()
    if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
        return {"ok": False, "error": "that time does not exist"}
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return {"ok": False, "error": "that date does not exist"}
    line = f"{date} {int(hour):02d}:{minute} {text.strip()}"
    path = calendar_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "message": "Saved.", "month": month_view(date[:7])}


def month_view(month: str = "") -> dict[str, Any]:
    today = datetime.now()
    try:
        year, number = (int(part) for part in month.split("-"))
        first = datetime(year, number, 1)
    except (ValueError, TypeError):
        first = datetime(today.year, today.month, 1)
    if first.month == 12:
        following = datetime(first.year + 1, 1, 1)
    else:
        following = datetime(first.year, first.month + 1, 1)
    days = (following - first).days

    events: dict[str, list[str]] = {}
    for date, time_text, text in read_events():
        events.setdefault(date, []).append(f"{time_text} {text}")

    return {
        "month": first.strftime("%Y-%m"),
        "label": first.strftime("%B %Y"),
        "days": days,
        "first_weekday": first.weekday(),  # Monday = 0
        "today": today.strftime("%Y-%m-%d") if same_month(first, today) else "",
        "events": events,
    }


def same_month(first: datetime, other: datetime) -> bool:
    return first.year == other.year and first.month == other.month


# -- clipboard --------------------------------------------------------------
# Nook keeps clipboard history in memory only; LEON does the same.

_cf_unicode = 13
_clip_lock = threading.Lock()
_clip_history: list[tuple[float, str]] = []


def _user32() -> Any:
    windll = getattr(ctypes, "windll", None)
    return getattr(windll, "user32", None) if windll is not None else None


def read_clipboard() -> str:
    user32 = _user32()
    if user32 is None:
        return ""
    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(_cf_unicode)
        if not handle:
            return ""
        pointer = user32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            user32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def write_clipboard(text: str) -> bool:
    user32 = _user32()
    kernel32 = _kernel32()
    if user32 is None or kernel32 is None:
        return False
    payload = text[:MAX_TEXT]
    size = (len(payload) + 1) * ctypes.sizeof(ctypes.c_wchar)
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(0x0042, size)  # GMEM_MOVEABLE | GMEM_ZEROINIT
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return False
        try:
            ctypes.memmove(pointer, ctypes.create_unicode_buffer(payload), size)
        finally:
            kernel32.GlobalUnlock(handle)
        return bool(user32.SetClipboardData(_cf_unicode, handle))
    finally:
        user32.CloseClipboard()


def grab_clipboard() -> dict[str, Any]:
    text = read_clipboard().strip()
    if not text:
        return {"ok": False, "error": "the clipboard is empty or not text"}
    with _clip_lock:
        _clip_history.insert(0, (time.time(), text[:MAX_TEXT]))
        del _clip_history[CLIP_HISTORY:]
    return {"ok": True, "items": clip_items(), "message": "Copied into the history."}


def clip_items() -> list[dict[str, Any]]:
    with _clip_lock:
        return [
            {
                "when": datetime.fromtimestamp(stamp).strftime("%H:%M"),
                "text": text,
            }
            for stamp, text in _clip_history
        ]


# -- notes ------------------------------------------------------------------


def note_files() -> list[Path]:
    folder = skills.notes_dir()
    try:
        return sorted(folder.glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    except OSError:
        return []


def note_list() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for path in note_files()[:20]:
        try:
            head = path.read_text(encoding="utf-8").splitlines()[0]
        except (OSError, IndexError):
            head = path.stem
        items.append({"name": path.stem, "title": head.lstrip("# ").strip()})
    return items


def note_read(name: str) -> dict[str, Any]:
    for path in note_files():
        if path.stem == name:
            try:
                return {"ok": True, "name": name, "text": path.read_text(encoding="utf-8")}
            except OSError as exc:
                return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "there is no note with that name"}


# -- quick launch -----------------------------------------------------------


def launch(target: str) -> dict[str, Any]:
    wanted = target.strip()
    if not wanted:
        return {"ok": False, "error": "nothing to open"}

    decision = check(wanted, Tier.ACT)
    if not decision.allowed:
        return {"ok": False, "error": f"refused: {decision.reason}"}

    app = skills.APPS.get(wanted.lower())
    if app is not None:
        return _start(app, wanted)

    if wanted.lower().startswith(("http://", "https://")):
        try:
            webbrowser.open(wanted)
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "message": f"Opened {wanted}."}

    if wanted.lower().startswith("ms-settings:"):
        return _start(wanted, wanted)

    path = Path(os.path.expandvars(wanted)).expanduser()
    if path.exists():
        return _start(str(path), path.name)
    return {"ok": False, "error": "that app, folder or page is not on this PC"}


def _start(target: str, label: str) -> dict[str, Any]:
    try:
        if target.endswith(":") or os.path.isdir(target):
            os.startfile(target)  # noqa: S606 - allowlisted or existing path
        else:
            subprocess.Popen([target])  # noqa: S603 - app comes from the allowlist
    except OSError as exc:
        return {"ok": False, "error": f"could not open {label}: {exc}"}
    return {"ok": True, "message": f"Opened {label}."}


# -- colour picker ----------------------------------------------------------

_last_colour: dict[str, Any] = {"hex": "", "rgb": ""}


def pick_colour() -> dict[str, Any]:
    global _last_colour
    user32 = _user32()
    gdi32 = getattr(getattr(ctypes, "windll", None), "gdi32", None)
    if user32 is None or gdi32 is None:
        return {"ok": False, "error": "the colour picker needs Windows"}
    point = _Point()
    if not user32.GetCursorPos(ctypes.byref(point)):
        return {"ok": False, "error": "the cursor position was unavailable"}
    hdc = user32.GetDC(None)
    if not hdc:
        return {"ok": False, "error": "the screen could not be read"}
    try:
        packed = gdi32.GetPixel(hdc, point.x, point.y)
    finally:
        user32.ReleaseDC(None, hdc)
    if packed == 0xFFFFFFFF:
        return {"ok": False, "error": "the screen could not be read"}
    red, green, blue = packed & 0xFF, (packed >> 8) & 0xFF, (packed >> 16) & 0xFF
    _last_colour = {
        "hex": f"#{red:02X}{green:02X}{blue:02X}",
        "rgb": f"rgb({red}, {green}, {blue})",
    }
    write_clipboard(_last_colour["hex"])
    return {"ok": True, "colour": _last_colour, "message": "Copied as hex."}


# -- optional modules -------------------------------------------------------

_NEEDS: dict[str, tuple[str, str]] = {
    "voice": (
        "sounddevice",
        "Recording needs the microphone package. Run `uv add sounddevice` and reopen the dock.",
    ),
}


def _missing(tool_id: str) -> dict[str, Any] | None:
    module, message = _NEEDS[tool_id]
    try:
        __import__(module)
    except ImportError:
        return {"ok": False, "error": message}
    return None


def record_voice(seconds: int) -> dict[str, Any]:
    missing = _missing("voice")
    if missing is not None:
        return missing
    import wave  # noqa: PLC0415 - only used when recording

    import sounddevice  # noqa: PLC0415 - optional dependency

    duration = max(1, min(120, seconds))
    target_dir = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Music" / "Voice memos"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"memo-{datetime.now():%Y%m%d-%H%M%S}.wav"
        with wave.open(str(target), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(44100)
            with sounddevice.RawInputStream(
                samplerate=44100, channels=1, dtype="int16", blocking=True
            ) as stream:
                remaining = duration
                while remaining > 0:
                    chunk, _ = stream.read(44100 * min(1, remaining))
                    handle.writeframes(chunk)
                    remaining -= 1
    except Exception as exc:  # noqa: BLE001 - microphone failures are many
        return {"ok": False, "error": f"recording failed: {type(exc).__name__}: {exc}"}
    return {"ok": True, "message": f"Saved {target.name}.", "path": str(target)}


# -- dispatch ---------------------------------------------------------------


def _act_awake(action: str, arg: str) -> dict[str, Any]:
    if action == "off":
        return _awake_off()
    try:
        minutes = int(arg or "0")
    except ValueError:
        return {"ok": False, "error": "minutes must be a number"}
    return _awake_on(minutes)


def _act_calc(action: str, arg: str) -> dict[str, Any]:
    answer = calculate(arg)
    return {"ok": True, "answer": answer, "expression": arg.strip()}


def _act_system(action: str, arg: str) -> dict[str, Any]:
    return {"ok": True, "state": _system_state()}


def _act_qr(action: str, arg: str) -> dict[str, Any]:
    return make_qr(arg)


def _act_calendar(action: str, arg: str) -> dict[str, Any]:
    if action == "add":
        return add_event(arg)
    return {"ok": True, "month": month_view(arg)}


def _act_clipboard(action: str, arg: str) -> dict[str, Any]:
    if action == "copy":
        ok = write_clipboard(arg)
        return {"ok": ok, "message": "Copied." if ok else "the clipboard refused the text"}
    if action == "clear":
        with _clip_lock:
            _clip_history.clear()
        return {"ok": True, "items": []}
    return grab_clipboard()


def _act_notes(action: str, arg: str) -> dict[str, Any]:
    if action == "read":
        return note_read(arg)
    return {"ok": True, "notes": note_list()}


def _act_launch(action: str, arg: str) -> dict[str, Any]:
    return launch(arg)


def _act_colour(action: str, arg: str) -> dict[str, Any]:
    return pick_colour()


def _act_voice(action: str, arg: str) -> dict[str, Any]:
    try:
        seconds = int(arg or "10")
    except ValueError:
        seconds = 10
    return record_voice(seconds)


def _act_media(action: str, arg: str) -> dict[str, Any]:
    """Now playing: artwork, transport, volume, scrub and the lyric line due now."""
    if action == "lines":
        return media.lines()
    if action == "save":
        return media.save_lyrics(arg)
    if action == "art":
        return media.art()
    if action == "seek":
        try:
            seconds = float(arg)
        except ValueError:
            return {"ok": False, "error": "a position in seconds is needed"}
        return media.seek(seconds)
    if action == "volume":
        try:
            percent = int(float(arg))
        except ValueError:
            return {"ok": False, "error": "a volume from 0 to 100 is needed"}
        return media.set_volume(percent)
    if action in ("playpause", "play", "pause", "next", "previous"):
        return media.control(action)
    return media.state()


def _act_screen(action: str, arg: str) -> dict[str, Any]:
    """The words in the front window, or a picture of the whole screen."""
    if action == "shot":
        return screen.capture()
    return screen.text()


_HANDLERS: dict[str, Any] = {
    "awake": _act_awake,
    "calc": _act_calc,
    "system": _act_system,
    "qr": _act_qr,
    "calendar": _act_calendar,
    "clipboard": _act_clipboard,
    "notes": _act_notes,
    "launch": _act_launch,
    "colour": _act_colour,
    "voice": _act_voice,
    "screen": _act_screen,
    "media": _act_media,
}


def act(tool_id: str, action: str, arg: str = "") -> dict[str, Any]:
    """Run one tile action. Never raises: the UI always gets a result."""
    if tool_id == "timer":
        return _timer(action, arg)
    handler = _HANDLERS.get(tool_id)
    if handler is None:
        return {"ok": False, "error": f"there is no tool called '{tool_id}'"}
    tool = _INDEX[tool_id]
    # A pasted lyric sheet is the user's data, not an instruction, so the policy
    # reads the action rather than the text: a song title cannot trip the
    # prompt-injection guard and block its own save.
    subject = tool_id if (tool_id == "media" and action == "save") else f"{tool_id} {arg}".strip()
    decision = check(subject, tool.tier)
    if not decision.allowed:
        return {"ok": False, "error": f"refused: {decision.reason}"}
    try:
        result: dict[str, Any] = handler(action, arg)
    except Exception as exc:  # noqa: BLE001 - a tile must not take the dock down
        return {"ok": False, "error": f"{tool_id} failed: {type(exc).__name__}"}
    if decision.ask and result.get("ok"):
        result["asked"] = decision.reason
    return result


def _timer(action: str, arg: str) -> dict[str, Any]:
    """The countdown itself lives in the page; Python only makes the sound."""
    if action == "beep":
        try:
            import winsound  # noqa: PLC0415 - Windows only

            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except (ImportError, RuntimeError):
            return {"ok": True, "silent": True}
        return {"ok": True}
    return {"ok": True}


def snapshot() -> list[dict[str, Any]]:
    """Everything the grid needs to draw itself, badges included."""
    calendar_today = month_view()
    today = calendar_today["today"]
    awake = _awake_state()
    system = _system_state()
    badges = {
        "awake": "on" if awake["on"] else "off",
        "system": f"{system['cpu']}%",
        "calendar": str(len(calendar_today["events"].get(today, []))) if today else "",
        "clipboard": str(len(clip_items())),
        "notes": str(len(note_files())),
        "colour": _last_colour["hex"][1:] if _last_colour["hex"] else "",
    }
    items: list[dict[str, Any]] = []
    for tool in TOOLS:
        items.append(
            {
                "id": tool.id,
                "name": tool.name,
                "glyph": tool.glyph,
                "size": tool.size,
                "blurb": tool.blurb,
                "badge": badges.get(tool.id, ""),
                "needs": _NEEDS.get(tool.id, ("", ""))[0],
            }
        )
    return items


def state(tool_id: str) -> dict[str, Any]:
    """The opening payload for one tile."""
    if tool_id == "awake":
        return {"ok": True, "state": _awake_state()}
    if tool_id == "system":
        return {"ok": True, "state": _system_state()}
    if tool_id == "calendar":
        return {"ok": True, "month": month_view()}
    if tool_id == "clipboard":
        return {"ok": True, "items": clip_items()}
    if tool_id == "notes":
        return {"ok": True, "notes": note_list()}
    if tool_id == "colour":
        return {"ok": True, "colour": _last_colour}
    if tool_id == "media":
        return media.state()
    if tool_id == "screen":
        held = inbox.listing()
        return {
            "ok": True,
            "window": screen.foreground_title(),
            "held": held,
            "held_note": inbox.describe(held),
        }
    if tool_id in _NEEDS:
        missing = _missing(tool_id)
        if missing is not None:
            return missing
        return {"ok": True}
    if tool_id == "launch":
        return {"ok": True, "apps": sorted(skills.APPS)}
    if tool_id not in _INDEX:
        return {"ok": False, "error": "no such tool"}
    return {"ok": True}


def parse(payload: str) -> dict[str, Any]:
    """Read a JSON payload from the page, or say why not."""
    if not payload.strip():
        return {}
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
