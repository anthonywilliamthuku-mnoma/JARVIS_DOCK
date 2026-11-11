"""How loud the PC is, for the island's waveform.

The waveform has to follow what the PC is actually playing - a class on a call,
a video, a song with no lyric file - so LEON listens to the speaker's loopback
device rather than to the microphone. Nothing is written to disk and only a
level leaves this module.

The capture runs on its own thread at about 40 frames a second. The reader is
deliberately forgiving: a device that disappears, a driver that refuses the
format, or a PC where the package is missing all mean "no level", never a crash
in the dock.
"""

from __future__ import annotations

import array
import math
import struct
import sys
import threading
import time

SAMPLE_RATE = 48_000
CHUNK = 1024
GAIN = 3.0
DECAY_S = 0.30
HINT = "The waveform follows the speakers, which needs `uv add pyaudiowpatch`."

_lock = threading.Lock()
_level = 0.0
_stamp = 0.0
_thread: threading.Thread | None = None
_stop = threading.Event()
_problem = ""


def available() -> bool:
    """Whether the loopback reader can be installed here."""
    try:
        import pyaudiowpatch  # noqa: F401 - probing the import
    except ImportError:
        return False
    return True


def level_from(frames: bytes, gain: float = GAIN) -> float:
    """A 0-1 level from interleaved 16-bit samples, for a bar display."""
    width = len(frames) - (len(frames) % 2)
    if width <= 0:
        return 0.0
    samples = array.array("h", frames[:width])
    if sys.byteorder != "little":  # pragma: no cover - Windows is little-endian
        samples.byteswap()
    total = 0.0
    count = 0
    for sample in samples:
        value = float(sample)
        total += value * value
        count += 1
    if count == 0:
        return 0.0
    rms = math.sqrt(total / count) / 32768.0
    if rms <= 1e-5:
        return 0.0
    scaled = float(rms * gain) ** 0.62
    return float(round(min(1.0, max(0.0, scaled)), 3))


def _publish(value: float) -> None:
    global _level, _stamp
    with _lock:
        _level = value
        _stamp = time.perf_counter()


def level() -> float:
    """The most recent level, decayed so a dry stream falls silent."""
    with _lock:
        value, stamp = _level, _stamp
    if value <= 0.0 or stamp <= 0.0:
        return 0.0
    age = time.perf_counter() - stamp
    return 0.0 if age > DECAY_S * 4 else round(value * math.exp(-age / DECAY_S), 3)


def _worker(stop: threading.Event) -> None:
    global _problem
    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        _problem = HINT
        return
    audio = pyaudio.PyAudio()
    try:
        device = audio.get_default_wasapi_loopback()
        rate = int(device["defaultSampleRate"]) or SAMPLE_RATE
        channels = max(1, int(device["maxInputChannels"]))
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=int(device["index"]),
            frames_per_buffer=CHUNK,
        )
        try:
            while not stop.is_set():
                chunk = stream.read(CHUNK, exception_on_overflow=False)
                _publish(level_from(chunk))
        finally:
            stream.stop_stream()
            stream.close()
    except Exception as exc:  # noqa: BLE001 - a sound card can fail in many ways
        _problem = f"{type(exc).__name__}: {exc}"
    finally:
        audio.terminate()
        _publish(0.0)


def start() -> bool:
    """Begin measuring, once. Returns whether a reader is running."""
    global _thread
    if not available():
        return False
    with _lock:
        if _thread is not None and _thread.is_alive():
            return True
        _stop.clear()
        _thread = threading.Thread(target=_worker, args=(_stop,), name="leon-audio", daemon=True)
        _thread.start()
    return True


def stop() -> None:
    global _thread
    _stop.set()
    thread = _thread
    if thread is not None and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=1.5)
    _thread = None
    _publish(0.0)


def problem() -> str:
    """Why the reader is not producing levels, if it knows."""
    return _problem


def hint() -> str:
    """One line for the UI when the waveform has nothing to follow."""
    if available():
        return problem() or "the speakers are quiet"
    return HINT


__all__ = [
    "HINT",
    "available",
    "hint",
    "level",
    "level_from",
    "problem",
    "start",
    "stop",
]
_ = struct  # keep the import set intentional for future formats
