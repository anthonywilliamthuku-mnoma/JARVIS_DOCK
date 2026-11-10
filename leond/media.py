"""What Windows is playing, and the lyrics that go with it.

The media tile reads the system media session (the same one the volume flyout
shows), so it works with whatever player the user has, and asks
:mod:`leond.lyrics` for the line that matches the current position. Nothing is
downloaded and nothing is fetched from the network.
"""

from __future__ import annotations

import asyncio
from typing import Any

from leond import lyrics

HINT = (
    "Reading what is playing needs Windows media support. Run `uv add winsdk` and reopen the dock."
)


def available() -> bool:
    """Whether the Windows media bindings are installed."""
    try:
        import winsdk.windows.media.control  # noqa: F401 - probing the import
    except ImportError:
        return False
    return True


def _manager() -> Any:
    from winsdk.windows.media.control import (  # noqa: PLC0415 - Windows only
        GlobalSystemMediaTransportControlsSessionManager,
    )

    return GlobalSystemMediaTransportControlsSessionManager


def _status() -> Any:
    from winsdk.windows.media.control import (  # noqa: PLC0415 - Windows only
        GlobalSystemMediaTransportControlsSessionPlaybackStatus,
    )

    return GlobalSystemMediaTransportControlsSessionPlaybackStatus


def _run(awaitable: Any, timeout: float) -> Any:
    """Wait for a Windows async call without touching the caller's loop."""

    async def guarded() -> Any:
        return await asyncio.wait_for(awaitable, timeout)

    return asyncio.run(guarded())


async def _session() -> Any:
    manager = await _manager().request_async()
    return manager.get_current_session() if manager is not None else None


async def _read() -> dict[str, Any] | None:
    session = await _session()
    if session is None:
        return None
    props = await session.try_get_media_properties_async()
    playing = False
    position = 0.0
    duration = 0.0
    try:
        playing = session.get_playback_info().playback_status == _status().PLAYING
    except Exception:  # noqa: BLE001 - a player may not report playback info
        playing = False
    try:
        timeline = session.get_timeline_properties()
        position = max(0.0, timeline.position.total_seconds())
        duration = max(0.0, (timeline.end_time - timeline.start_time).total_seconds())
    except Exception:  # noqa: BLE001 - not every player exposes a timeline
        pass
    return {
        "title": (props.title or "").strip(),
        "artist": (props.artist or "").strip(),
        "album": (props.album_title or "").strip(),
        "playing": bool(playing),
        "position": round(position, 2),
        "duration": round(duration, 2),
    }


async def _send(action: str) -> bool:
    session = await _session()
    if session is None:
        return False
    if action == "playpause":
        return bool(await session.try_toggle_play_pause_async())
    if action == "next":
        return bool(await session.try_skip_next_async())
    if action == "previous":
        return bool(await session.try_skip_previous_async())
    return False


def _lyrics_part(track: dict[str, Any] | None) -> dict[str, Any]:
    if not track:
        return {"key": "", "count": 0, "index": -1}
    artist, title = track.get("artist", ""), track.get("title", "")
    lines = lyrics.load(artist, title)
    return {
        "key": lyrics.key(artist, title),
        "count": len(lines),
        "index": lyrics.index_at(lines, float(track.get("position", 0.0))) if lines else -1,
    }


def state() -> dict[str, Any]:
    """The playing track, its position and which lyric line is current."""
    if not available():
        return {"ok": False, "error": HINT}
    try:
        track = _run(_read(), 2.5)
    except Exception:  # noqa: BLE001 - the session may vanish mid-read
        return {"ok": False, "error": "the media session could not be read just now"}
    return {
        "ok": True,
        "playing": bool(track and track["playing"]),
        "track": track,
        "lyrics": _lyrics_part(track),
    }


def lines() -> dict[str, Any]:
    """Every lyric line for the current track, plus the current index."""
    if not available():
        return {"ok": False, "error": HINT}
    try:
        track = _run(_read(), 2.5)
    except Exception:  # noqa: BLE001 - the session may vanish mid-read
        return {"ok": False, "error": "the media session could not be read just now"}
    if not track:
        return {"ok": True, "key": "", "lines": [], "index": -1}
    artist, title = track["artist"], track["title"]
    saved = lyrics.load(artist, title)
    return {
        "ok": True,
        "key": lyrics.key(artist, title),
        "lines": [line.text for line in saved],
        "index": lyrics.index_at(saved, track["position"]) if saved else -1,
    }


def control(action: str) -> dict[str, Any]:
    """Pause, play, skip. The same buttons the keyboard's media keys send."""
    if not available():
        return {"ok": False, "error": HINT}
    if action not in ("playpause", "next", "previous"):
        return {"ok": False, "error": f"'{action}' is not a media control"}
    try:
        worked = _run(_send(action), 2.5)
    except Exception:  # noqa: BLE001 - the player may have closed
        return {"ok": False, "error": "the player did not answer"}
    return {"ok": worked, "error": "" if worked else "the player did not take that"}


def save_lyrics(text: str) -> dict[str, Any]:
    """Store an .lrc for the track that is playing now."""
    if not text.strip():
        return {"ok": False, "error": "there is nothing to save"}
    if not available():
        return {"ok": False, "error": HINT}
    try:
        track = _run(_read(), 2.5)
    except Exception:  # noqa: BLE001 - the session may vanish mid-read
        return {"ok": False, "error": "the media session could not be read just now"}
    if not track:
        return {
            "ok": False,
            "error": "nothing is playing, so there is no track to attach lyrics to",
        }
    target, saved = lyrics.save(track["artist"], track["title"], text)
    if not saved:
        return {
            "ok": False,
            "error": "no `[00:12.34]` timestamps were found, so the lyrics could not be synced",
        }
    return {"ok": True, "saved": len(saved), "file": target.name}
