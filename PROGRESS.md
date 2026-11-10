# Progress

Single source of truth for LEON. Re-read at the start of every session.

## Done
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
- No tray icon and no global hotkey yet.
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
