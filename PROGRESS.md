# Progress

Single source of truth for LEON. Re-read at the start of every session.

## Done
- **Phase 0 (foundations):** project skeleton, `pyproject.toml` (uv, ruff, mypy strict, pytest), CI workflow, `ARCHITECTURE.md`, `DECISIONS.md`, `SKILLS.md`, this file. Tagged `phase-0-done`.
- **Island dock (D-008, D-012):** a transparent 520x60 pill pinned to the top centre of the screen that grows into the conversation. Frameless, always on top, draggable, WebView2 through `pywebview`; no Node, no Rust, no open ports.
- **Brain (D-009):** `leond/brain.py` streams from any local OpenAI-compatible server and understands tool calls. Default model is the small local one.
- **Facts (D-010):** `leond/facts.py` reads the clock, time zone, region, OS build, memory and disk from Windows and injects them into every turn.
- **Skills and approvals (D-011):** `leond/skills.py` (local_time, local_place, system_report, open_app, write_note, run_powershell) and `leond/agent.py`, which checks policy, raises an Allow / Deny card for T2+, and bounds a turn to three steps.
- **Audit:** hash-chained JSONL at `%APPDATA%\LEON\audit.jsonl`, with `verify()`.
- **Verified on 2026-11-10:**
  - `ruff check`, `ruff format --check`, `mypy` and `pytest` (52 tests) pass.
  - The island opened at 520x60 on a 1366x768 desktop.
  - "What is the current time and date right now?" answered with the real local
    time (20:08, UTC+03:00, E. Africa Standard Time).
  - "How much free disk space is left?" made the model call `system_report` and
    answer with the real figure (92.8 GB free of 232.9 GB, 73% memory in use).

## In progress
- Phase 1 (brain and core loop) is essentially complete for a single-user dock.

## Next 5 actions
1. Add a global summon hotkey (`Win+Alt+L`) with a small Win32 `RegisterHotKey`
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
