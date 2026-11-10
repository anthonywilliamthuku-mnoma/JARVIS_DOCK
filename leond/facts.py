"""Live facts about this machine, read from Windows itself.

Small models cannot be trusted to know the date, let alone where the machine is
or how much disk is free. Every fact here is read at call time and handed to the
model in its system prompt, so answers about "now" and "here" come from the PC
rather than from the model's imagination.
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
from datetime import datetime
from typing import Any

try:  # Windows only; the import keeps the module testable elsewhere.
    import winreg
except ImportError:  # pragma: no cover - only on non-Windows
    winreg = None  # type: ignore[assignment]

_GEO_KEY = r"Control Panel\International\Geo"
_TZ_KEY = r"System\CurrentControlSet\Control\TimeZoneInformation"


def _reg(path: str, name: str) -> str:
    if winreg is None:
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                value, _ = winreg.QueryValueEx(key, name)
        except OSError:
            return ""
    return str(value) if value is not None else ""


def now() -> datetime:
    return datetime.now().astimezone()


def local_time() -> str:
    """The current local date and time, with its offset and zone."""
    moment = now()
    offset = moment.utcoffset()
    total = int(offset.total_seconds()) if offset else 0
    sign = "+" if total >= 0 else "-"
    hours, minutes = divmod(abs(total) // 60, 60)
    return (
        f"{moment:%A, %d %B %Y, %H:%M} "
        f"(UTC{sign}{hours:02d}:{minutes:02d}, {moment.tzname() or 'local time'})"
    )


def country() -> str:
    """The Windows region country code, for example ``KE``."""
    return _reg(_GEO_KEY, "Name")


def time_zone() -> str:
    return _reg(_TZ_KEY, "TimeZoneKeyName") or (now().tzname() or "")


def local_place() -> str:
    """Country and time zone as Windows reports them."""
    code = country()
    zone = time_zone()
    parts = []
    if code:
        parts.append(f"Windows region country code {code}")
    if zone:
        parts.append(f"time zone {zone}")
    locale_name = os.environ.get("LANG") or ""
    if locale_name:
        parts.append(f"locale {locale_name}")
    return ", ".join(parts) if parts else "the region is not reported by Windows"


def _memory() -> tuple[float, float]:
    """(used_percent, total_gb); zeros when unavailable."""
    if platform.system() != "Windows":
        return 0.0, 0.0

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("memory_load", ctypes.c_ulong),
            ("total_phys", ctypes.c_ulonglong),
            ("avail_phys", ctypes.c_ulonglong),
            ("total_page", ctypes.c_ulonglong),
            ("avail_page", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong),
            ("avail_virtual", ctypes.c_ulonglong),
            ("avail_extended", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.length = ctypes.sizeof(MemoryStatus)
    kernel32: Any = ctypes.windll.kernel32
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return 0.0, 0.0
    total_gb = status.total_phys / (1024**3)
    return float(status.memory_load), round(total_gb, 1)


def disk_free() -> tuple[float, float]:
    """(free_gb, total_gb) for the system drive."""
    root = os.environ.get("SYSTEMDRIVE", "C:") + "\\"
    try:
        usage = shutil.disk_usage(root)
    except OSError:
        return 0.0, 0.0
    return round(usage.free / (1024**3), 1), round(usage.total / (1024**3), 1)


def system_report() -> str:
    load, total_ram = _memory()
    free_disk, total_disk = disk_free()
    root = os.environ.get("SYSTEMDRIVE", "C:")
    lines = [
        f"Operating system: {platform.system()} {platform.release()} ({platform.version()})",
        f"Machine: {platform.machine()}, {os.cpu_count() or 'unknown'} logical processors",
    ]
    if total_ram:
        lines.append(f"Memory: {load:.0f}% in use of {total_ram} GB")
    if total_disk:
        lines.append(f"Disk {root}: {free_disk} GB free of {total_disk} GB")
    return "\n".join(lines)


def snapshot() -> str:
    """A compact block for the system prompt."""
    return (
        "Facts read from this PC right now. Use them instead of guessing; do not "
        "invent a different time, place or amount.\n"
        f"- Local time: {local_time()}\n"
        f"- Place: {local_place()}\n"
        f"- System: {system_report().replace(chr(10), ' | ')}"
    )
