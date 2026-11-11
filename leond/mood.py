"""Which face LEON wears, and what the island shows while it wears it.

The page draws; this module decides. Keeping the decision here means it can be
tested without a window, a pointer or a speaker, and that the same rule set
covers the collapsed island and the expanded corner face.

The rules, in priority order:

1. An attention ping outranks everything: LEON wants an answer.
2. A turn in flight is ``think``.
3. Playing with a lyric line to highlight hides the face entirely (``lyrics``):
   the song is the thing to look at, not LEON.
4. Playing anything else - a video, a call, a browser tab - shows the waveform,
   which reacts to whatever the PC is actually making a noise about.
5. Files left on the dock are worth a ``glad`` face and a count.
6. Sound without a media session still gets the waveform.
7. Otherwise: calm, and watching the pointer.
"""

from __future__ import annotations

from dataclasses import dataclass

MOODS = ("calm", "alert", "glad", "blank", "listen", "think")
MODES = ("face", "wave", "lyrics", "files", "glow")


@dataclass(frozen=True, slots=True)
class Mood:
    """One face, one island mode, and the line shown on hover."""

    mood: str
    mode: str
    note: str = ""
    held: int = 0


def decide(
    *,
    busy: bool = False,
    attention: bool = False,
    playing: bool = False,
    lyrics: int = -1,
    level: float = 0.0,
    held: int = 0,
) -> Mood:
    """Pick the face and the island mode from what the PC is doing."""
    if attention:
        return Mood("alert", "glow", "asking for you", held)
    if busy:
        return Mood("think", "face", "working", held)
    if playing and lyrics >= 0:
        return Mood("listen", "lyrics", "singing along", held)
    if playing:
        return Mood("listen", "wave", "listening to the PC", held)
    if held > 0:
        return Mood("glad", "files", f"{held} file{'s' if held > 1 else ''} held", held)
    if level > 0.02:
        return Mood("listen", "wave", "hearing something", held)
    return Mood("calm", "face", "ready", held)


def payload(mood: Mood) -> dict[str, object]:
    """The shape the page's ``window.leon.mood`` expects."""
    return {"mood": mood.mood, "mode": mood.mode, "note": mood.note, "held": mood.held}
