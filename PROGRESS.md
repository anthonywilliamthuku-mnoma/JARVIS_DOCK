# Progress

Single source of truth for LEON. Re-read at the start of every session.

## Done
- **Verified on 2026-11-11 (faces, sound, media, screen) — on this PC, not in a mock:**
  - `pytest` 142 passed, `ruff check`/`format --check` clean, `mypy --platform win32` clean on 37
    files, and `node --check` passes on all three page scripts.
  - `uv run leon` opened the real dock: 223 x 43 at 571,0 on the 1366 x 768 desktop. The island
    wore the calm drop face; a click at its centre opened it to 470 x 170 (and made LEON the front
    window, as designed), where the round face appears in the top-right corner only while open.
  - The waveform is driven by real speakers, not a mock: a 220 Hz tone played through the default
    output moved the loopback meter to a peak of **0.997**, and the island switched from the face to
    five purple bars while it sounded, then back.
  - The Media tile read the session that was actually open — *BIRDS OF A FEATHER* by Billie Eilish —
    with its **real artwork** (a 234,846-byte PNG read from the session thumbnail), the scrub bar at
    0:04 of 3:30 and the system volume at **64**, matching Nook's player.
  - Screen: `BitBlt` capture works (1366 x 768 BMP in `%APPDATA%\LEON\screens`), and UI Automation
    returns the front window's title and control labels. `Windows.Media.Ocr` answers *Class not
    registered* on this PC (it needs MSIX package identity), which is why D-017 reads UIA first.
  - A real bug was found and fixed by the tests: pycaw (comtypes, STA) followed by a WinRT call in
    one thread made the media read hang rather than fail. All WinRT calls now run on one MTA thread
    (`leond/winrt.py`, D-018).
  - Not verified: the audible ping end to end (the sequence is unit-tested and the glow is shown in
    `leond/ui/_show.html`), hover-to-open on the real desktop (a click was used), and the lyrics mode
    hiding the face (it needs a `.lrc` for the playing track).
- **Verified on 2026-11-11 (agent and dock):** 102 tests pass; `ruff check`,
  `ruff format --check` and `mypy --platform win32` are clean on 25 files; the
  page passes `node --check`. A 31-minute headless soak drove the real
  `DockApi` through 1,085 open/act cycles over all thirteen tiles and 19 chat
  turns with no leak, no stuck thread and an intact audit chain; the native
  window itself still needs Windows. `leond/ui/_show.html` renders the dock in
  five states at real size against a mocked bridge.
- **Phase 0 (foundations):** project skeleton, `pyproject.toml` (uv, ruff, mypy strict, pytest), CI workflow, `ARCHITECTURE.md`, `DECISIONS.md`, `SKILLS.md`, this file. Tagged `phase-0-done`.
- **Dock shell (D-008, D-012):** recreated from Nook 0.4.2 as a transparent **223 x 43** glass capsule at the top centre, flush with the screen edge. Hover opens it (120 ms), leaving folds it (250 ms), a click pins it, and it grows into a **470 x 170** panel. Frameless, always on top, draggable, WebView2 through `pywebview`; no Node, no Rust, no open ports.
- **Brain (D-009):** `leond/brain.py` streams from any local OpenAI-compatible server and understands tool calls. Default model is the small local one.
- **Facts (D-010):** `leond/facts.py` reads the clock, time zone, region, OS build, memory and disk from Windows and injects them into every turn.
- **Skills and approvals (D-011):** `leond/skills.py` (local_time, local_place, system_report, open_app, write_note, run_powershell) and `leond/agent.py`, which checks policy, raises an Allow / Deny card for T2+, and bounds a turn to three steps.
- **Audit:** hash-chained JSONL at `%APPDATA%\LEON\audit.jsonl`, with `verify()`.
- **Verified on 2026-11-10:**
  - `ruff check`, `ruff format --check`, `mypy` and `pytest` (52 tests) pass.
  - The dock opened at 520x60 on a 1366x768 desktop (superseded by the 223 x 43 shell below).
  - "What is the current time and date right now?" answered with the real local
    time (20:08, UTC+03:00, E. Africa Standard Time).
  - "How much free disk space is left?" made the model call `system_report` and
    answer with the real figure (92.8 GB free of 232.9 GB, 73% memory in use).

- **Verified on 2026-11-10 (Nook shell):**
  - `pytest` now includes `tests/test_dock_geometry.py`: the collapsed dock is
    exactly 223 x 43, centred, flush with the top edge, and both states share
    one centre line (57 tests pass).
  - `ruff check` and `ruff format --check` pass. `mypy` is clean for the real
    target (`--platform win32`, 19 files); on a Linux machine it reports
    `winreg`, `os.startfile` and `ctypes.windll` as missing, which is expected.
  - Both states were rendered in a browser at true size and inspected:
    the capsule carries the clock, dot, LEON mark, state and chevron; the open
    panel shows the intro, three quick actions, composer and stats line.
  - Not yet seen on Windows: the native window is transparent and frameless, so
    the capsule's corners are composited by the desktop (unverified on this PC).

- **Tool tiles (D-013), wave 1:** a Chat/Tools tab pair and a bento grid of 12 tiles backed by `leond/tools.py`. Working end to end: keep awake, timer/stopwatch, calculator (percentages, powers, factorial, hex/binary, units, temperatures), system monitor, calendar, QR codes, clipboard (memory only), notes, quick launch, colour picker. Voice memo is coded against `sounddevice` but unverified; the text extractor reports its missing dependency and is not wired up.
- **Verified on 2026-11-10 (tools):**
  - `pytest` 81 passed, including `tests/test_tools.py` (calculator, calendar
    round-trip and rejection, QR, notes, launch refusals, platform fallbacks).
  - `ruff check`, `ruff format --check` and `mypy --platform win32` clean.
  - The grid, the system meters and the calendar month view were rendered in a
    browser with mocked bridge data and inspected; two layout bugs were found
    and fixed there (the grid stayed visible under a tool page, and the glyph
    column picked up colour emoji).

- **Hovering opens the dock, clicking keeps it open (D-012):** the hover path no
  longer focuses the message box, which is what used to make a hovered dock
  impossible to fold again — `canFold()` refuses while the composer has focus.
  Focus now follows a click (or typing), and clicking anywhere in the open panel
  pins it.
- **Media tile with synced lyrics (D-014):** now playing and its transport
  buttons come from the Windows media session (`winsdk`, SMTC); the playhead
  comes from the session timeline, and the lyric line that belongs to that
  second is highlighted. Lyrics are the user's own `.lrc` files in
  `%APPDATA%\LEON\lyrics` (`Artist - Title.lrc`), pasted once from the tile's
  **Lyrics** box. Nothing is downloaded.
- **The turn's history is no longer duplicated:** each tool checkpoint used
  to re-send every earlier step's sentence, so a two-step answer handed the
  model its own preamble twice and the model echoed it. A checkpoint now holds
  only what that step said, the closing entry holds only the last step, and the
  context window never begins with a tool result whose question was trimmed
  away (servers reject that pairing). The dock also drops the empty bubble a
  tool-only turn used to leave.
- **The open panel is 470 x 170, and the tiles were shrunk to fit it:** the
  Chat/Tools switch moved into the header row, the grid is six across and two
  rows (all twelve tiles, no scrolling, 9 px labels that do not clip), and the
  approval card became an opaque sheet over the composer so nothing shows
  through it. Every tool page fits its 101 px body without scrolling except the
  calendar, which scrolls about 100 px for its add field and event list because
  a whole month plus controls cannot fit 127 px; the month grid itself is what
  you see first.
- **Verified on 2026-11-10 (open panel):**
  - Rendered at true size in a browser with a mocked bridge: collapsed
    223 x 43 with the tabs hidden, open 470 x 170, grid overflow 0, body
    overflow 0, six tiles per row, and the approval card 87 px tall inside the
    panel without covering the header.
  - `tests/test_dock_launch.py` runs `dock.run()` against a faked window and
    asserts what a real launch does: the capsule is created 223 x 43 at y = 0
    and centred, `set_open(True)` resizes it to 470 x 170 without moving the top
    edge, and the bridge methods the page calls all exist.
  - **Not launched here:** this is a Linux VM with no display and no GTK/QT, so
    `uv run leon` stops in `webview.initialize()` before a window exists. The
    native window, transparency and hover-open still need the user's PC.
- **Verified on 2026-11-10 (hover and media), in a browser with a mocked
  bridge that resizes the frame like the native window does:**
  - hover expands 223 x 43 to 470 x 170 without focusing the composer, leaving
    folds it back after the 250 ms grace, and a click keeps it open after the
    pointer leaves; clicking the panel pins it too.
  - the grid draws 13 tiles in two rows at 470 x 170 with no scrolling, no
    horizontal overflow and no clipped labels (long ones wrap to a second line).
  - the Media tile renders track, artist, buttons and lyric lines, and its
    highlighted line advances as the mocked playhead moves (index 2 to 3).
  - **Not verified on hardware:** the SMTC read, the transport buttons and the
    playhead all need Windows and a player; `tests/test_lyrics.py` covers the
    parsing, the line matching and the file store instead.

## In progress
- Phase 1 (brain and core loop) is essentially complete for a single-user dock.
- Nook module parity: 10 of its modules are ported; see the parity table in `README.md` for the rest.

## Next 5 actions
1. Wave 2 of the tools: media (SMTC) and text extraction (screen capture plus
   `winsdk` OCR), then voice memo verified on real hardware.
2. Add a global summon hotkey (`Win+Alt+L`) with a small Win32 `RegisterHotKey`
   wrapper, since pywebview has no API for one.
2. Persist the conversation in SQLite so closing the island does not forget it.
3. Add a tray icon with Show / Kill switch, so LEON can be stopped without the
   island being open.
4. Add a settings page inside the island (model, endpoint, accent) instead of
   editing `%APPDATA%\LEON\config.toml` by hand.
5. Write the tool-call eval: a fixed prompt set run against the configured
   model, so a weaker model can be rejected on evidence.

## Blocked
- Answer quality is limited by the hardware. The 4B heretic model is installed
  but needs about 180 s for 8 tokens on this CPU (D-009).

## Known gaps
- Two global hotkeys via Win32 `RegisterHotKey`, both confirmed `registered` in the audit log:
  `Win+Alt+V` opens the dock and starts the mic, `Win+Alt+J` toggles spoken replies.
- `Win+J` and `Win+Alt+M` are already owned by other apps on this PC (error 1409), so they are not used.
- Pressing `Win+Alt+V` on the running dock was tested: the dock expanded to 470 x 170 and the audit logged
  `voice | hotkey Win+Alt+V | listening`.
- Pressed `Win+Alt+J` on the running dock: the audit logged `voice | spoken replies | off`, then a
  second press logged `on`. The toggle works by key; speech is left ON.
- The dock is pinned: `easy_drag=False`, so it stays centred at the top edge (217 x 50 at x=574, y=0
  on 1366 x 768) and cannot be dragged away.
- The mic now sends by itself: `startListening()` calls `send()` after the transcript lands in the
  composer, so `Win+Alt+V` then saying "open Notepad" runs the command with no second click.
- No tray icon yet.
- The dock's native transparency and hover-to-open were verified in a browser,
  not yet on the Windows desktop: the first `uv run leon` on the PC is the real
  test. If transparency misbehaves, set `transparent=False` in `leond/dock.py`
  (D-012).
- Conversation history lives in memory only.
- `run_powershell` is the only way to change the PC beyond opening apps and
  writing notes; the elevated helper (Phase 4) does not exist.
- Approval cards time out after 120 seconds and count as a denial.

## How to run
```
uv sync --locked
uv run leon
```

## How to run tests
```
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

## Round: agent acts, island size, research

- Agent acts: `config.py` system prompt no longer says LEON cannot change the PC; it calls skills directly and relies on Allow cards. Not yet tested against a live request.
- Island size: collapsed dock is now 217 x 50 (`dock.py`, `style.css`); geometry tests updated. Dock launched at 217x50 on the PC.
- Lyrics: browser playback reports a session, but the "(1) Instagram" tab has no artist, so no lyric lookup. TODO(leon): retest with a song playing and its .lrc saved.
- Voice commands: TODO(leon). Research: Vosk (Apache-2.0, offline, Windows wheel) is the candidate. Not integrated.
- Phone Link: TODO(leon). No public API. Notification integration is a Limited Access Feature, approval by email to Microsoft. SMS requires Windows.Devices.Sms or a Phone Link UI path. Not integrated.

## Voice commands (Vosk)

- `leond/voice.py`: push-to-talk. Records the default microphone until a pause, transcribes offline with Vosk, returns text. No audio is written to disk.
- Model: `vosk-model-small-en-us-0.15` (41 MB) in `%APPDATA%\LEON\voice\model`. Not in the repo.
- Dock: a mic button next to Send (`index.html`, `app.js`, `style.css`) calls `DockApi.listen()`. The transcript goes into the text box for review; Send is still required.
- Dependency: `vosk>=0.3.45` (Apache-2.0), added to `pyproject.toml`/`uv.lock`; mypy override added.
- Tests: `tests/test_voice.py` (threshold and missing-model paths). Spoken-phrase accuracy is NOT tested: TODO(leon) speak a command and check the transcript.

## Agent acts (live check)

- Live: the dock's chat path ran `open_app` (audit `ok`) for "Open Notepad", and Notepad started. The prompt was not changed.

## Dock size and spoken replies

- Collapsed island is 217 x 50 again (the 225 x 56 step was reverted); pill CSS and tests follow.
- Replies are now spoken aloud through Windows' built-in speech (`voice.speak`, System.Speech via PowerShell, no new dependency, runs in the background).
- Root cause of the 201 x 100 / 209 x 100 sizes: pywebview's default `min_size` is (200, 100) and the WinForms backend applies it as MinimumSize. `create_window` now passes `min_size=(WIDTH, COLLAPSED_H)`.
- Measured live: window 217 x 50 at x=574, y=0 (matches the log). Screenshot `artifacts/island.png` is 217 x 50.
- Spoken replies can use ElevenLabs (`ELEVENLABS_API_KEY` env var, optional `ELEVENLABS_VOICE_ID`;
  default voice Rachel). Any failure falls back to the built-in Windows voice, and without a key
  nothing leaves the PC. Tests: `tests/test_voice.py` (key set / unset paths).
- TODO(leon): ElevenLabs live check returns HTTP 402 (account out of credits,
  key itself accepted). Add credits in ElevenLabs, then replies speak with the smooth
  voice with no code change; until then the built-in voice is the fallback.
- Verified twice through the real reply path (speech on, then off): with `speak_replies = true` `voice.speak` ran once and a PowerShell speech process was launched; with it false the reply came back and no speech process started.
- TODO(leon): whether the audio is audible (volume, voice choice) is not verified; no one has listened.
- Dock appearance update: removed the shell's white rim and inset highlight; hid the idle `ready` label and arrow; kept hover-to-open, clock and activity pip; moved the sole face to the top-right beside LEON. Native window restarted and measured 217 x 50 at (574, 0). Visual corner appearance still needs user confirmation.

- Fenn 0.5.0 update: Pomodoro presets and stopwatch laps in the Timer tile; long media titles glide like Fenn's; dock geometry unchanged at 217 x 50 collapsed and 470 x 170 open.
- Shazam-style Identify tile: captures 10 seconds from the Windows speaker/loopback output and sends it to AudD. Set AUDD_API_TOKEN in the Windows user environment; without it the tile explains what is missing. Live identification still needs a real token and a playing song.
- Optional PiP preview tile: captures the front window at low frame rate for browser/player videos. This is a preview frame, not Windows moving the video element into the island; true PiP from another app would need browser/player cooperation or a native capture pipeline.
- High-modding surface: `%APPDATA%\LEON\mods` is the mod folder and `leond/mods.py` lists installed `.py` mods. Mod execution hooks are the next step, after the API is designed.
