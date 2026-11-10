"""Time-synced lyrics, from the user's own .lrc files.

LEON never downloads lyrics: they are copyrighted, and the dock is offline by
design. It reads ``.lrc`` files from ``%APPDATA%/LEON/lyrics``, matched by
"Artist - Title.lrc", and hands the media tile the timestamps it needs to keep
one line highlighted as the track plays.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from leond.config import config_dir

# A lyric file is small; anything larger is not one.
MAX_BYTES = 200_000

# [mm:ss], [mm:ss.xx] and the rare [mm:ss:xx]; the brackets must hold digits,
# so [ar:...], [ti:...] and [offset:...] are metadata and fall through.
_STAMP = re.compile(r"\[(\d{1,3}):(\d{1,2}(?:[.:]\d{1,3})?)\]")

# Everything Windows does not allow in a file name, plus path separators.
_UNSAFE = re.compile(r"[^A-Za-z0-9 ()\[\].,'&_+-]+")


@dataclass(frozen=True, slots=True)
class Line:
    """One lyric line and the second it starts at."""

    at: float
    text: str


def folder() -> Path:
    """Where the user's lyric files live."""
    return config_dir() / "lyrics"


def parse(text: str) -> tuple[Line, ...]:
    """Every timed line in an .lrc file, earliest first.

    A line may carry several timestamps (``[00:12.00][01:04.50]chorus``), which
    becomes one :class:`Line` per stamp. Untimed and metadata lines are dropped.
    """
    found: list[Line] = []
    for raw in text.splitlines():
        stamps = _STAMP.findall(raw)
        if not stamps:
            continue
        body = _STAMP.sub("", raw).strip()
        for minutes, seconds in stamps:
            at = int(minutes) * 60 + float(seconds.replace(":", "."))
            found.append(Line(round(at, 3), body))
    found.sort(key=lambda line: line.at)
    return tuple(found)


def index_at(lines: tuple[Line, ...], seconds: float) -> int:
    """Which line to highlight at ``seconds``; -1 before the first one."""
    index = -1
    for position, line in enumerate(lines):
        if line.at > seconds + 0.05:
            break
        index = position
    return index


def name(artist: str, title: str) -> str:
    """The file name for a track, safe on Windows and stable across calls."""
    stem = f"{artist} - {title}".strip(" -")
    safe = _UNSAFE.sub("_", stem).strip(" ._")[:80]
    return f"{safe or 'track'}.lrc"


def path(artist: str, title: str) -> Path:
    return folder() / name(artist, title)


def load(artist: str, title: str) -> tuple[Line, ...]:
    """The saved lyrics for a track, or nothing if there are none."""
    try:
        text = path(artist, title).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    return parse(text[:MAX_BYTES])


def save(artist: str, title: str, text: str) -> tuple[Path, tuple[Line, ...]]:
    """Write an .lrc for this track and return where it went and what it held."""
    target = path(artist, title)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text[:MAX_BYTES], encoding="utf-8")
    return target, parse(text[:MAX_BYTES])


def key(artist: str, title: str) -> str:
    """A short identifier the page compares to know when lyrics changed."""
    return name(artist, title)
