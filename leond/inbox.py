"""Files left on the dock for LEON.

Nook's island shows what the dock is holding. LEON's equivalent is an inbox
folder: anything put in ``%APPDATA%/LEON/inbox`` counts as held, the island
shows how many, and LEON can list them when asked. Nothing is ever deleted
from it by the dock itself.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from leond.config import config_dir

MAX_SHOWN = 20


def folder() -> Path:
    """Where held files live."""
    return config_dir() / "inbox"


def listing() -> list[dict[str, Any]]:
    """Held files, newest first. An unreadable folder is simply empty."""
    try:
        entries = [entry for entry in folder().iterdir() if entry.is_file()]
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        return []
    found: list[dict[str, Any]] = []
    for entry in entries:
        try:
            info = entry.stat()
        except OSError:
            continue
        found.append(
            {
                "name": entry.name,
                "size": info.st_size,
                "when": datetime.fromtimestamp(info.st_mtime).strftime("%d %b %H:%M"),
            }
        )
    found.sort(key=lambda item: item["when"], reverse=True)
    return found[:MAX_SHOWN]


def count() -> int:
    """How many files the dock is holding."""
    return len(listing())


def describe(items: list[dict[str, Any]] | None = None) -> str:
    """A short sentence for the model."""
    held = listing() if items is None else items
    if not held:
        return "The dock is not holding any files."
    names = ", ".join(str(item["name"]) for item in held[:8])
    more = "" if len(held) <= 8 else f" and {len(held) - 8} more"
    return f"The dock is holding {len(held)} file(s): {names}{more}."
