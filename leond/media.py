"""What Windows is playing, its artwork, and the lyrics that go with it.

The media tile reads the system media session (the same one the volume flyout
shows), so it works with whatever player the user has, and asks
:mod:`leond.lyrics` for the line that matches the current position. Nothing is
downloaded and nothing is fetched from the network.

The transport and the scrub bar go back through the same session, the volume
goes to the default output device, and the artwork is read from the session's
thumbnail into a data URL the page can show without a second request.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from leond import lyrics, winrt

HINT = (
    "Reading what is playing needs the Windows media bindings. Run "
    "`uv add winrt-windows-media-control` and reopen the dock."
)
VOLUME_HINT = "The volume slider needs `uv add pycaw` and the Windows audio service."
MAX_ART_BYTES = 1_500_000
TICKS_PER_SECOND = 10_000_000


def available() -> bool:
    """Whether the Windows media bindings are installed."""
    return winrt.available()


def _manager() -> Any:
    return winrt.klass("windows.media.control", "GlobalSystemMediaTransportControlsSessionManager")


def _status() -> Any:
    return winrt.klass(
        "windows.media.control", "GlobalSystemMediaTransportControlsSessionPlaybackStatus"
    )


def _run(make: Callable[[], Any], timeout: float) -> Any:
    """Await one WinRT call on the apartment thread that owns it."""
    return winrt.run_async(make, timeout)


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
    if action == "play":
        return bool(await session.try_play_async())
    if action == "pause":
        return bool(await session.try_pause_async())
    if action == "next":
        return bool(await session.try_skip_next_async())
    if action == "previous":
        return bool(await session.try_skip_previous_async())
    return False


async def _seek(seconds: float) -> bool:
    session = await _session()
    if session is None:
        return False
    ticks = int(max(0.0, seconds) * TICKS_PER_SECOND)
    return bool(await session.try_change_playback_position_async(ticks))


async def _art() -> str:
    """The session's thumbnail as a data URL, or an empty string."""
    session = await _session()
    if session is None:
        return ""
    props = await session.try_get_media_properties_async()
    reference = props.thumbnail
    if reference is None:
        return ""
    stream = await reference.open_read_async()
    size = int(stream.size)
    if size <= 0 or size > MAX_ART_BYTES:
        return ""
    from winrt.windows.storage.streams import DataReader  # noqa: PLC0415 - Windows only

    reader = DataReader(stream)
    await reader.load_async(size)
    payload = bytearray(size)
    reader.read_bytes(payload)
    head = bytes(payload[:8])
    if head == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif head[:2] == b"\xff\xd8":
        mime = "image/jpeg"
    else:
        return ""
    return f"data:{mime};base64,{base64.b64encode(bytes(payload)).decode('ascii')}"


# -- volume -----------------------------------------------------------------


def _endpoint() -> Any | None:
    winrt.apartment()  # comtypes wants an apartment on this thread too
    try:
        from pycaw.pycaw import AudioUtilities  # noqa: PLC0415 - optional dependency
    except ImportError:
        return None
    try:
        return AudioUtilities.GetSpeakers().EndpointVolume
    except Exception:  # noqa: BLE001 - the audio service may be off
        return None


def volume() -> int:
    """The output volume as 0-100, or -1 when it cannot be read."""
    endpoint = _endpoint()
    if endpoint is None:
        return -1
    try:
        return int(round(float(endpoint.GetMasterVolumeLevelScalar()) * 100))
    except Exception:  # noqa: BLE001 - a device can vanish mid-read
        return -1


def set_volume(percent: int) -> dict[str, Any]:
    """Set the output volume, 0-100."""
    endpoint = _endpoint()
    if endpoint is None:
        return {"ok": False, "error": VOLUME_HINT}
    try:
        value = max(0, min(100, int(percent)))
        endpoint.SetMasterVolumeLevelScalar(value / 100.0, None)
    except Exception:  # noqa: BLE001 - the device refused
        return {"ok": False, "error": "the audio device did not take that volume"}
    return {"ok": True, "volume": value}


# -- lyrics -----------------------------------------------------------------


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
    """The playing track, its position, the volume and the current lyric line."""
    if not available():
        return {"ok": False, "error": HINT, "volume": -1, "volume_hint": VOLUME_HINT}
    try:
        track = _run(_read, 2.5)
    except Exception:  # noqa: BLE001 - the session may vanish mid-read
        return {
            "ok": False,
            "error": "the media session could not be read just now",
            "volume": volume(),
            "volume_hint": VOLUME_HINT,
        }
    return {
        "ok": True,
        "playing": bool(track and track["playing"]),
        "track": track,
        "lyrics": _lyrics_part(track),
        "volume": volume(),
        "volume_hint": VOLUME_HINT,
    }


def now() -> dict[str, Any]:
    """Just what the island needs: is anything playing, and which line.

    The dock asks this about once a second, so it skips the volume and the
    artwork that the tile wants.
    """
    if not available():
        return {"ok": False, "playing": False, "lyrics": {"key": "", "count": 0, "index": -1}}
    try:
        track = _run(_read, 2.0)
    except Exception:  # noqa: BLE001 - the session may vanish mid-read
        return {"ok": False, "playing": False, "lyrics": {"key": "", "count": 0, "index": -1}}
    return {"ok": True, "playing": bool(track and track["playing"]), "lyrics": _lyrics_part(track)}


def lines() -> dict[str, Any]:
    """Every lyric line for the current track, plus the current index."""
    if not available():
        return {"ok": False, "error": HINT}
    try:
        track = _run(_read, 2.5)
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


def art() -> dict[str, Any]:
    """The artwork for the current track, ready to drop into a background."""
    if not available():
        return {"ok": False, "error": HINT}
    try:
        data = _run(_art, 4.0)
    except Exception:  # noqa: BLE001 - the player may have closed
        return {"ok": False, "error": "the artwork could not be read"}
    if not data:
        return {"ok": False, "error": "this player did not share any artwork"}
    return {"ok": True, "data_url": data}


def seek(seconds: float) -> dict[str, Any]:
    """Move the playhead, as dragging the scrub bar does."""
    if not available():
        return {"ok": False, "error": HINT}
    wanted = max(0.0, float(seconds))
    try:
        moved = _run(lambda: _seek(wanted), 2.5)
    except Exception:  # noqa: BLE001 - the player may have closed
        return {"ok": False, "error": "the player did not answer"}
    return {
        "ok": moved,
        "position": round(wanted, 2),
        "error": "" if moved else "the player cannot seek",
    }


def control(action: str) -> dict[str, Any]:
    """Pause, play, skip. The same buttons the keyboard's media keys send."""
    if not available():
        return {"ok": False, "error": HINT}
    if action not in ("playpause", "play", "pause", "next", "previous"):
        return {"ok": False, "error": f"'{action}' is not a media control"}
    try:
        worked = _run(lambda: _send(action), 2.5)
    except Exception:  # noqa: BLE001 - the player may have closed
        return {"ok": False, "error": "the player did not answer"}
    return {"ok": worked, "error": "" if worked else "the player did not take that"}


def length() -> float:
    """The current track's duration in seconds, or 0."""
    if not available():
        return 0.0
    try:
        track = _run(_read, 2.5)
    except Exception:  # noqa: BLE001 - the session may vanish mid-read
        return 0.0
    return float(track["duration"]) if track else 0.0


def save_lyrics(text: str) -> dict[str, Any]:
    """Store an .lrc for the track that is playing now."""
    if not text.strip():
        return {"ok": False, "error": "there is nothing to save"}
    if not available():
        return {"ok": False, "error": HINT}
    try:
        track = _run(_read, 2.5)
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


__all__ = [
    "HINT",
    "VOLUME_HINT",
    "art",
    "available",
    "control",
    "length",
    "lines",
    "now",
    "save_lyrics",
    "seek",
    "set_volume",
    "state",
    "volume",
]
_ = timedelta  # the type the WinRT seek call documents, kept for readers
