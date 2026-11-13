"""High-modding surface for LEON.

Mods are intentionally small Python files the user drops into
``%APPDATA%\\LEON\\mods``. LEON does not execute them yet; this module only
lists what is installed so the dock and README can describe the extension
folder honestly. A future mod API will import these modules and let them add
tiles, shortcuts, face moods, and quick settings without forking LEON.
"""

from __future__ import annotations

import os
from pathlib import Path


def mods_dir() -> Path:
    """Where user mods live."""
    base = Path(os.environ.get("APPDATA", str(Path.home())))
    return base / "LEON" / "mods"


def list_mods() -> list[dict[str, str]]:
    """Installed mod files, name only."""
    folder = mods_dir()
    if not folder.is_dir():
        return []
    return [{"name": path.name} for path in sorted(folder.glob("*.py")) if path.is_file()]


__all__ = ["list_mods", "mods_dir"]
