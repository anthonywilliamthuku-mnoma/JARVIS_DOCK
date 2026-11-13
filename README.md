# LEON

A local-first assistant for Windows with its own dock: a small always-on-top
panel with LEON inside it. It runs on your machine, against a model you host,
and it keeps a tamper-evident log of every turn.

No account, no cloud, no telemetry, no open ports.

## Run it

```bash
uv sync --locked
uv run leon
```

The dock opens as a frameless panel pinned above other windows. Type a message
and press **Enter**; **Shift+Enter** adds a line; **Esc** stops a reply that is
still arriving.

## The model

LEON speaks to any local server that offers the OpenAI-compatible
`/v1/chat/completions` endpoint: Ollama, llama.cpp's server, LM Studio, vLLM.

The default is a small Ollama model so the dock starts quickly on modest
hardware:

```
qwen2.5-0.5b-heretic:latest
```

Point it at something else in `%APPDATA%\LEON\config.toml`:

```toml
endpoint = "http://127.0.0.1:11434/v1"
model = "hf.co/mradermacher/DeepSeek-V4-Pro-Qwen3.5-4B-UNCENSORED-heretic-GGUF:Q4_K_M"
context = 2048
temperature = 0.4
accent = "#7C5CFF"
```

Environment variables win over the file: `LEON_MODEL`, `LEON_ENDPOINT`,
`LEON_CONTEXT`, `LEON_TEMPERATURE`.

**Measured on this PC** (Intel HD Graphics 520, 8 GB RAM, CPU inference):
the 4B model answered 8 tokens in about 180 seconds, so it is installed but
not usable for conversation here. The 0.5B model replies in a few seconds.
Speed depends mostly on the CPU and on how much memory is free; no GPU is used.

## The dock

The dock is a glass capsule **223 × 43** pinned to the top centre of the
screen, flush with the edge like a notch. It carries a live clock, a face, a
status pip and what LEON is doing, and nothing else.

### The face

Six moods, drawn as inline SVG and small enough for the capsule: a grey drop
(calm), a blue triangle (alert), an orange blob (glad), a black circle, a green
pill (listening) and a brown flower (thinking). The face blinks, drifts a few
pixels and turns its eyes toward the pointer, wherever the pointer is on the
desktop. Opened, the same face appears again as a round face in the top-right
corner, and only while the dock is open.

What it shows comes from `leond/mood.py`, in this order:

| The PC is… | The island shows |
|---|---|
| asking for you (a ping) | alert face, and a glow that pulses with the ping |
| answering a question | thinking face |
| playing a song with a lyric line | the face hides and a ♪ stays, until playback stops |
| playing anything else (a video, a call) | a waveform that follows the speakers |
| holding files for LEON | glad face, and how many |
| making a sound with no media session | the waveform |
| quiet | calm face, watching the pointer |

- **Hover** it and it opens after a 120 ms debounce; move away and it folds
  after 250 ms.
- **Click** it to pin it open, and click anything inside the panel to keep it
  open the same way. Click the capsule again, or press **Esc**, to fold it.
- Open, it grows downwards into a 470 × 170 panel: the header row keeps the
  clock, the state and the Chat/Tools switch, and the tiles shrink to a
  seven-across, two-row grid so the whole panel fits without scrolling.
- Hovering never takes the keyboard: only a click focuses the message box, so a
  hovered dock can still fold itself when you move away.
- It stays open while a reply is streaming, while you type, and while an
  approval card is waiting — it will not fold under your hands.

The shell's behaviour and look are recreated from **Nook 0.4.2** (MIT): the
capsule-to-panel shell, hover/pin interaction, charcoal glass gradient, 1 px rim
and top highlight, and the clock in the pill. The rendering is LEON's own
HTML/CSS, not Nook's Rust code, so the dock stays a single Python process.

## What it does today

- **Real facts.** Every turn carries a live block read from Windows: local time
  and UTC offset, time zone, region, operating system, memory use and free disk
  space. Ask "what time is it" and the answer comes from the PC, not the model.
- **Real tasks.** The model can call the skills below, and each call is checked
  by the policy engine first.
- **It can see the screen.** `look_at_screen` reads the front window's title and
the words and controls in it (UI Automation), falling back to OCR and then to a
saved screenshot. `type_text` and `click_at` let it act on what it sees; both
need an Allow card.
- **It can get your attention.** `get_attention` pauses whatever is playing,
pings twice, glows the island in time with the ping, and resumes the music when
you touch the dock.
- **It reacts to sound.** The waveform follows the speakers (WASAPI loopback),
so a class, a video or a song all move it — not just the media session.
- Streaming replies, typed out as the model produces them.
- A live status line with time to first word and tokens per second.
- Stop button and Esc, which close the connection instead of waiting.
- Audit log at `%APPDATA%\LEON\audit.jsonl`: hash-chained, so edits are
  detectable. It records skill names, sizes and outcomes, never message text.

| Skill | Tier | What it does |
|---|---|---|
| `local_time` | T0 | Current date, time and time zone |
| `local_place` | T0 | Country and time zone as Windows reports them |
| `system_report` | T0 | OS, processors, memory use, free disk space |
| `open_app` | T1 | Opens an app from a fixed allowlist (Notepad, Calculator, Explorer…) |
| `write_note` | T1 | Saves a Markdown note under `%APPDATA%\LEON\notes` |
| `run_powershell` | T2 | Runs a command — **only after you press Allow** |
| `look_at_screen` | T0 | The front window's title, words and controls |
| `list_held_files` | T0 | What is sitting in the dock's inbox folder |
| `save_screenshot` | T1 | Saves a picture of the screen to LEON's folder |
| `get_attention` | T1 | Pauses playback, pings, glows, and resumes |
| `type_text` | T2 | Types into the front window — **Allow required** |
| `click_at` | T2 | Clicks at a screen position — **Allow required** |

T0 skills run immediately. T2 actions raise an approval card in the island
showing the exact command; an unanswered card is a refusal, and the hard-deny
list in `leond/policy.py` refuses destructive commands outright with no
override.

## Tools: the tile grid

Open the dock and switch to **Tools** for a bento grid of utilities, like
Nook's. Every tile is a real backend action on this PC, checked by the policy
engine and written to the audit log (the log records the call, never your text).

| Tile | What it does |
|---|---|
| Keep awake | Holds the display on for 15 min, an hour, or until switched off |
| Timer | Countdown and stopwatch, with a chime at zero |
| Calculator | Sums, `20% of 150`, `2^10`, `5!`, hex and binary, unit and temperature conversion |
| System | CPU, memory and free space, live while open |
| Calendar | Month view and events, saved in `%APPDATA%\LEON\calendar.txt` |
| QR code | Any text or link as a scannable code |
| Clipboard | Grabs the current text and keeps the last 30, in memory only |
| Notes | Everything LEON has saved as Markdown |
| Quick launch | Allowlisted apps, URLs, `ms-settings:` pages and existing folders |
| Colour picker | Reads the pixel under the cursor and copies the hex |
| Voice memo | Records the microphone to `Music\Voice memos` |
| Screen | The front window's words, or a picture of the whole screen |
| Media | The track Windows is playing, its buttons, and its lyric line in sync |
| Identify | Shazam-style song ID from the speakers (AudD token required) |
| PiP preview | Optional live preview of the front browser/player window |

The Windows-only pieces ship as optional wheels that only install on Windows:
`winrt-windows-media-control` (the media session), `winrt-windows-media-ocr`
(screen pixels, where Windows allows it), `pyaudiowpatch` (the speakers' loopback
for the waveform) and `pycaw` (the volume slider). Voice memo additionally needs
`uv add sounddevice`. Everything else runs on the standard library and
`ctypes`.

**On this PC** `Windows.Media.Ocr` answers *Class not registered* — the OCR
namespace needs MSIX package identity, which a plain `uv run` app does not have.
The Screen tile therefore reads UI Automation first, which needs no identity and
returns the real control labels; OCR is the fallback where it works, and a
screenshot is the last resort (D-017).

## Lyrics, in sync

The Media tile is Nook's player, rebuilt: the session's artwork, track and
artist, a scrub bar with both times (click to seek), previous / play-pause /
next, a volume slider with its number, and the lyric sheet underneath. It reads
whatever player Windows is showing in its media flyout, asks the session for the
playhead, and highlights the lyric line that belongs to that second. LEON never downloads lyrics — they are copyrighted and the dock is
offline — so it reads your own `.lrc` files from `%APPDATA%\LEON\lyrics`, matched
as `Artist - Title.lrc`. Press **Lyrics** in the tile, paste a timestamped file,
and LEON stores it for that track and reuses it next time.

```
[00:12.34] first line
[00:17.90] the next one
```

## Nook 0.4.2 parity

Nook's shell is recreated; its modules are being ported one wave at a time
because they are written in Rust against Win32, DWM, `Windows.UI.Composition`,
`Windows.Media.Ocr` and SMTC, which Python reaches differently or not at all.

| Nook | LEON |
|---|---|
| Pill clock, hover/pin shell, glass | Done |
| Keep awake, timer, calculator, calendar, QR, clipboard, quick launch, colour picker, system monitor, notes | Done |
| Voice memo | Code present, needs `sounddevice`, unverified on hardware |
| Media (SMTC) with synced lyrics | Session read, transport and lyric sync written; needs `winsdk`, unverified on hardware |
| Text extractor (OCR) | Screen tile: UI Automation first, OCR and screenshot as fallbacks |
| Island moods, faces, waveform | Done — six faces, mouse-following eyes, loopback waveform |
| Settings page, tray icon, global hotkey | Not implemented |
| Phone link (adb/scrcpy, LocalSend) | Not implemented; needs external binaries |
| Wallpaper, draw on screen, Lens search, font detector | Not implemented |
| Plugin SDK (`plugin.toml` + any language) | Not implemented |
| Bento edit mode (drag/resize tiles) | Not implemented |

## Layout

```
leond/
  config.py     settings: TOML file plus environment overrides
  facts.py      live Windows facts (time, place, system, disk)
  brain.py      streaming client for local OpenAI-compatible servers, with tools
  skills.py     what LEON can do, each with a tier and a JSON schema
  tools.py      the tile grid's backends (Nook's utilities, rebuilt)
  media.py      now playing from the Windows media session: artwork, transport,
  shazam.py     speaker-output song identification via AudD
  pip.py        optional front-window preview frames for video
  mods.py       high-modding folder listing for %APPDATA%\LEON\mods
                seek, volume, and the lyric line for this second
  lyrics.py     .lrc parsing, the line for a given second, and the file store
  mood.py       which face LEON wears, and what the island shows
  audio.py      the speakers' loopback level, for the waveform
  cursor.py     where the pointer is, for the eyes
  screen.py     screen capture, UI Automation/OCR text, typing and clicking
  attention.py  pause, ping, glow, wait for an answer, put the music back
  inbox.py      files left on the dock
  winrt.py      the WinRT namespaces, and the one thread that owns them
  agent.py      one turn: check policy, ask if needed, run the skill, answer
  policy.py     permission tiers and the hard-deny list
  audit.py      hash-chained audit log
  dock.py       the island window and the methods the page may call
  ui/           index.html, style.css, app.js (no framework, no build step)
tests/          unit tests, no network needed
```

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

## Status

Phase 0 (foundations) is complete, and Phase 1 (brain and core loop) works:
model client, live facts, policy-gated skills with an approval card, audit log
and the dock shell. The elevated helper (Phase 4) is still to come. See
`PROGRESS.md` and `DECISIONS.md`.

## Shortcuts

Fenn-style shortcuts (registered with Windows when the dock is running):

- `Ctrl+Alt+N` — pin LEON open
- `Ctrl+Alt+T` — copy the front window's text
- `Ctrl+Alt+P` — copy the colour under the cursor
- `Alt+Space` — search / ask LEON
- `Ctrl+Alt+K` — calculator
- `Ctrl+Alt+D` — screen tools (draw fallback)
- `Ctrl+Alt+C` — keep awake
- `Ctrl+Alt+L` — screen tools (lens fallback)
- `Ctrl+Alt+R` — voice memo
- `Ctrl+Alt+G` — listen (Hey Fenn equivalent)

`Ctrl+Win` is not bound because Windows does not expose a lone modifier as a registerable hotkey.
