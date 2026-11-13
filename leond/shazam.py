"""Shazam-style song identification for the dock.

This does not use Apple's private Shazam API. It captures a short clip from
the Windows speaker/loopback output, then sends that clip to AudD's public
music-recognition API. Set ``AUDD_API_TOKEN`` in the Windows user environment;
the token is never written to disk or logged.

AudD is an online service. If there is no token, no network, or no match, the
function returns a friendly error instead of raising.
"""

from __future__ import annotations

import io
import json
import os
import struct
import time
import urllib.error
import urllib.request
import wave
from typing import Any

HINT = (
    "Shazam needs a free AudD token. Set AUDD_API_TOKEN in your Windows user "
    "environment, then reopen the dock."
)
DEFAULT_SECONDS = 10
AUDD_URL = "https://api.audd.io/"


def token() -> str:
    """The AudD token, cleaned the same way a pasted key would be."""
    return "".join(os.environ.get("AUDD_API_TOKEN", "").split()).strip("<>")


def available() -> bool:
    """Whether the loopback capture package is importable."""
    try:
        import pyaudiowpatch  # noqa: F401 - probing the import
    except ImportError:
        return False
    return True


def _rms(frames: bytes) -> float:
    count = len(frames) // 2
    if count == 0:
        return 0.0
    samples = struct.unpack(f"<{count}h", frames[: count * 2])
    total = sum(float(sample) * float(sample) for sample in samples)
    return float((total / count) ** 0.5 / 32768.0)


def _downmix_to_mono(frames: bytes, channels: int) -> bytes:
    if channels <= 1:
        return frames
    width = len(frames) - (len(frames) % (2 * channels))
    if width <= 0:
        return b""
    samples = struct.unpack(f"<{width // 2}h", frames[:width])
    mono = bytearray()
    for start in range(0, len(samples), channels):
        group = samples[start : start + channels]
        mono.extend(struct.pack("<h", int(sum(group) / len(group))))
    return bytes(mono)


def capture_clip(seconds: int = DEFAULT_SECONDS) -> tuple[bytes, int, int]:
    """Capture speaker output as WAV bytes, sample rate, and channels."""
    if not available():
        raise RuntimeError(HINT)
    import pyaudiowpatch as pyaudio  # noqa: PLC0415 - optional dependency

    audio = pyaudio.PyAudio()
    stream = None
    try:
        device = audio.get_default_wasapi_loopback()
        rate = int(device["defaultSampleRate"]) or 48000
        channels = max(1, int(device["maxInputChannels"]))
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=int(device["index"]),
            frames_per_buffer=1024,
        )
        chunks: list[bytes] = []
        deadline = time.time() + max(3, min(20, seconds))
        while time.time() < deadline:
            chunk = stream.read(1024, exception_on_overflow=False)
            if chunk:
                chunks.append(_downmix_to_mono(chunk, channels))
        pcm = b"".join(chunks)
        if _rms(pcm) < 0.004:
            raise RuntimeError("I did not hear enough music. Play a song and try again.")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(pcm)
        return buffer.getvalue(), rate, 1
    finally:
        if stream is not None:
            with _suppress():
                stream.stop_stream()
                stream.close()
        audio.terminate()


class _suppress:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> bool:
        return True


def _multipart(fields: dict[str, str], wav: bytes) -> tuple[bytes, str]:
    boundary = "----LEONShazamBoundary"
    body = bytearray()
    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        body.extend(value.encode())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="audio"; filename="clip.wav"\r\n')
    body.extend(b"Content-Type: audio/wav\r\n\r\n")
    body.extend(wav)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    return bytes(body), boundary


def _parse(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return {"ok": False, "error": "No song matched that clip."}
    apple_value = result.get("apple_music")
    apple: dict[str, Any] = apple_value if isinstance(apple_value, dict) else {}
    spotify_value = result.get("spotify")
    spotify: dict[str, Any] = spotify_value if isinstance(spotify_value, dict) else {}
    url = str(apple.get("url") or "")
    if not url:
        external_value = spotify.get("external_urls")
        external: dict[str, Any] = external_value if isinstance(external_value, dict) else {}
        url = str(external.get("spotify") or "")
    return {
        "ok": True,
        "title": str(result.get("title") or "Unknown title"),
        "artist": str(result.get("artist") or "Unknown artist"),
        "album": str(result.get("album") or ""),
        "release_date": str(result.get("release_date") or ""),
        "url": url,
        "artwork": str(apple.get("artwork") or ""),
    }


def identify(seconds: int = DEFAULT_SECONDS) -> dict[str, Any]:
    """Identify the song currently coming through the speakers."""
    key = token()
    if not key:
        return {"ok": False, "error": HINT}
    try:
        wav, _rate, _channels = capture_clip(seconds)
        fields = {
            "api_token": key,
            "return": "apple_music,spotify",
        }
        body, boundary = _multipart(fields, wav)
        request = urllib.request.Request(
            AUDD_URL,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "error": f"AudD answered HTTP {exc.code}; check the token or try another clip.",
        }
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return {"ok": False, "error": "Could not reach AudD to identify that clip."}
    except Exception as exc:  # noqa: BLE001 - the tile always gets a sentence
        return {"ok": False, "error": str(exc) or type(exc).__name__}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "AudD returned something unreadable."}
    return _parse(payload)


__all__ = ["DEFAULT_SECONDS", "HINT", "available", "capture_clip", "identify", "token"]
