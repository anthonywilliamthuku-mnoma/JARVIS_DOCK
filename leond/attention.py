"""Getting the user's attention: pause what is playing, ping, glow, wait.

LEON should be able to ask for a moment rather than waiting to be noticed. The
sequence is deliberately blunt and reversible:

1. If anything is playing, pause it. Nothing is heard over the ping, and the
   user has to look eventually.
2. Tell the page to glow, and play two short tones. The page pulses the island
   on the same beats the sound plays, so the glow and the ping read as one
   thing.
3. Wait for the user to touch the dock. Any click or key is an answer.
4. Put the music back the way it was.

Every step is injectable so the sequence can be tested without a speaker, a
media session or a window.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from leond import media

DEFAULT_TIMEOUT_S = 20.0
BEATS_MS = (0, 380, 760)
SILENT = "silent"


@dataclass(frozen=True, slots=True)
class Ping:
    """What one attention request did."""

    ok: bool
    answered: bool
    paused: bool
    reason: str

    def sentence(self) -> str:
        """One line for the model."""
        if not self.ok:
            return "LEON could not ask for attention."
        if self.answered:
            return "The user answered the ping." + (" Playback was resumed." if self.paused else "")
        if self.answered is False and self.paused:
            return "Nobody answered, so playback was resumed anyway."
        return "Nobody answered the ping."


def _no_emit(_name: str, _payload: object) -> None:
    """The default before the dock has registered itself."""


def _no_wait(_timeout: float) -> bool:
    """The default: nobody can answer, so do not block a skill on it."""
    return False


_emit: Callable[[str, object], None] = _no_emit
_wait: Callable[[float], bool] = _no_wait


def set_hooks(
    emit: Callable[[str, object], None] | None = None,
    wait: Callable[[float], bool] | None = None,
) -> None:
    """The dock registers how to reach the page and how to wait for an answer."""
    global _emit, _wait
    if emit is not None:
        _emit = emit
    if wait is not None:
        _wait = wait


def _is_playing() -> bool:
    return bool(media.state().get("playing"))


def _pause() -> bool:
    return bool(media.control("playpause").get("ok"))


def _beep(frequency: int, duration_ms: int) -> None:
    try:
        import winsound  # noqa: PLC0415 - Windows only
    except ImportError:
        return
    try:
        winsound.Beep(frequency, duration_ms)
    except (RuntimeError, ValueError):
        return


def _tones(beep: Callable[[int, int], None], beats: Sequence[int]) -> None:
    """Play the same beats the glow uses, so sound and screen agree."""
    started = time.perf_counter()
    for at in beats:
        gap = at / 1000.0 - (time.perf_counter() - started)
        if gap > 0:
            time.sleep(gap)
        beep(880, 85)
        beep(660, 100)


def ask(
    reason: str = "",
    *,
    is_playing: Callable[[], bool] | None = None,
    pause: Callable[[], bool] | None = None,
    emit: Callable[[str, object], None] | None = None,
    wait: Callable[[float], bool] | None = None,
    beep: Callable[[int, int], None] | None = None,
    beats: Sequence[int] = BEATS_MS,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> Ping:
    """Ask for attention: pause, ping, glow, and wait for an answer."""
    playing = is_playing or _is_playing
    toggle = pause or _pause
    tell = emit or _emit
    hold = wait or _wait
    sound = _beep if beep is None else beep
    text = reason.strip() or "may I have a moment?"

    paused = False
    try:
        if playing():
            paused = bool(toggle())
    except Exception:  # noqa: BLE001 - a missing media session is not a failure
        paused = False

    tell("attention", {"reason": text, "beats": list(beats)})
    threading.Thread(target=_tones, args=(sound, beats), name="leon-ping", daemon=True).start()

    answered = bool(hold(timeout))
    tell("attentionDone", {})
    if paused:
        toggle()
    return Ping(ok=True, answered=answered, paused=paused, reason=text)
