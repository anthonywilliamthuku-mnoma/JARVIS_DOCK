"""Voice commands: speak to LEON, transcribed offline with Vosk.

Push-to-talk. The page asks for one utterance; we record the default microphone
until the speaker goes quiet (or a time limit passes), transcribe it with a
small Vosk model kept under %APPDATA%\\LEON\\voice\\model, and return the text.
Nothing is sent to the network and no audio is written to disk.

The model is a download the user places themselves (see `MODEL_HINT`). If the
package, the model, or a microphone is missing, every call returns an error
string instead of raising, so the dock keeps running.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import struct
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

RATE = 16_000
CHUNK = 1600  # 0.1 s at 16 kHz
MAX_SECONDS = 8.0
SILENCE_S = 1.0
SPEECH_RMS = 0.012  # 0-1 full-scale RMS threshold for "someone is talking"
MODEL_HINT = (
    "Put a Vosk model in %APPDATA%\\LEON\\voice\\model "
    "(e.g. vosk-model-small-en-us-0.15 from alphacephei.com/vosk/models)."
)


def model_dir() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home())))
    return base / "LEON" / "voice" / "model"


def available() -> bool:
    """Whether the recogniser can run here: the package and a model are present."""
    try:
        import vosk  # noqa: F401 - probing the import
    except ImportError:
        return False
    return model_dir().is_dir()


def _rms(chunk: bytes) -> float:
    count = len(chunk) // 2
    if count == 0:
        return 0.0
    samples = struct.unpack(f"<{count}h", chunk[: count * 2])
    total = sum(float(s) * float(s) for s in samples)
    return math.sqrt(total / count) / 32768.0


def record_utterance() -> bytes:
    """Record from the default microphone until a pause after speech, or the limit."""
    import pyaudiowpatch as pyaudio

    audio = pyaudio.PyAudio()
    try:
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
        frames: list[bytes] = []
        heard = False
        quiet_since: float | None = None
        started = time.perf_counter()
        try:
            while time.perf_counter() - started < MAX_SECONDS:
                chunk = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(chunk)
                now = time.perf_counter()
                if _rms(chunk) >= SPEECH_RMS:
                    heard = True
                    quiet_since = None
                elif heard:
                    quiet_since = quiet_since or now
                    if now - quiet_since >= SILENCE_S:
                        break
        finally:
            stream.stop_stream()
            stream.close()
    finally:
        audio.terminate()
    return b"".join(frames) if heard else b""


def transcribe(pcm: bytes) -> str:
    """Offline speech-to-text for 16-kHz mono 16-bit PCM."""
    import vosk

    vosk.SetLogLevel(-1)
    model = vosk.Model(str(model_dir()))
    recognizer = vosk.KaldiRecognizer(model, RATE)
    recognizer.AcceptWaveform(pcm)
    result = json.loads(recognizer.FinalResult())
    return str(result.get("text", "")).strip()


ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel, a calm default voice
ELEVENLABS_TIMEOUT_S = 20.0


def _speak_system(spoken: str) -> None:
    """Say text aloud with the built-in Windows voice, without blocking.

    Uses the built-in System.Speech synthesiser, so nothing is installed and
    nothing leaves the PC. The text is passed through an environment variable,
    never spliced into the command, so reply text cannot inject PowerShell.
    """
    env = {**os.environ, "LEON_SPEAK": spoken}
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Rate = 1; $s.Speak($env:LEON_SPEAK); $s.Dispose()"
    )
    try:
        subprocess.Popen(  # noqa: S603 - fixed program and arguments
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except OSError:
        return


def _speak_elevenlabs(spoken: str) -> None:
    """Fetch ElevenLabs audio for the text and play it, else fall back.

    Runs on its own thread because the network call takes a moment. Any
    failure (no network, bad key, bad response) falls back to the built-in
    Windows voice so a reply is still heard. The API key is read only from
    the ``ELEVENLABS_API_KEY`` environment variable and is never logged.
    """
    path = ""
    try:
        voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "").strip() or ELEVENLABS_VOICE_ID
        body = json.dumps({"text": spoken, "model_id": "eleven_multilingual_v2"}).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            data=body,
            headers={
                "xi-api-key": os.environ.get("ELEVENLABS_API_KEY", "").strip(),
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=ELEVENLABS_TIMEOUT_S) as response:
            audio = response.read()
        if not audio:
            raise ValueError("empty audio response")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as handle:
            handle.write(audio)
            path = handle.name
        env = {**os.environ, "LEON_AUDIO": path}
        script = (
            "Add-Type -AssemblyName presentationCore; "
            "$m = New-Object System.Windows.Media.MediaPlayer; "
            "$m.Open([System.Uri]$env:LEON_AUDIO); $m.Play(); "
            "$end = (Get-Date).AddSeconds(120); "
            "while (-not $m.NaturalDuration.HasTimeSpan -and (Get-Date) -lt $end) "
            "{ Start-Sleep -Milliseconds 100 }; "
            "$len = $m.NaturalDuration.TimeSpan.TotalSeconds; "
            "if ($len -gt 0) { Start-Sleep -Seconds ($len + 0.5) } "
            "else { Start-Sleep -Seconds 10 }; "
            "$m.Close()"
        )
        subprocess.run(  # noqa: S603 - fixed program and arguments
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
    except Exception:  # noqa: BLE001 - any failure means the built-in voice
        _speak_system(spoken)
    finally:
        if path:
            with contextlib.suppress(OSError):
                Path(path).unlink(missing_ok=True)


def speak(text: str) -> None:
    """Say a reply aloud, without blocking.

    Uses ElevenLabs when the ``ELEVENLABS_API_KEY`` environment variable is
    set, otherwise the built-in Windows voice. The ElevenLabs call runs on a
    background thread and falls back to the built-in voice on any failure,
    so a reply is still heard.
    """
    spoken = " ".join(text.split())[:1000]
    if not spoken:
        return
    if os.environ.get("ELEVENLABS_API_KEY", "").strip():
        thread = threading.Thread(
            target=_speak_elevenlabs, args=(spoken,), name="leon-speak", daemon=True
        )
        thread.start()
    else:
        _speak_system(spoken)


def listen() -> dict[str, object]:
    """One push-to-talk turn: record, transcribe, and report what was heard."""
    if not available():
        return {"ok": False, "error": MODEL_HINT}
    try:
        pcm = record_utterance()
    except Exception as exc:  # noqa: BLE001 - a microphone can fail in many ways
        return {"ok": False, "error": f"microphone: {type(exc).__name__}: {exc}"}
    if not pcm:
        return {"ok": False, "error": "I didn't hear anything"}
    text = transcribe(pcm)
    if not text:
        return {"ok": False, "error": "I couldn't make that out"}
    return {"ok": True, "text": text}


__all__ = [
    "ELEVENLABS_VOICE_ID",
    "MODEL_HINT",
    "available",
    "listen",
    "model_dir",
    "record_utterance",
    "speak",
    "transcribe",
]
