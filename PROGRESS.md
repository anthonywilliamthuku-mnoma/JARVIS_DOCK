# Progress

Single source of truth for LEON. Re-read at the start of every session.

## Done
- **Phase 0 (foundations):** project skeleton, `pyproject.toml` (uv, ruff, mypy strict, pytest), CI workflow, `ARCHITECTURE.md`, `DECISIONS.md`, `SKILLS.md`, this file. Tagged `phase-0-done`.
- **Dock vertical slice (D-008):**
  - `leond/config.py`: TOML settings in `%APPDATA%/LEON/config.toml`, environment overrides, validation.
  - `leond/brain.py`: streaming client for local OpenAI-compatible servers, stdlib only, cancellable.
  - `leond/audit.py`: hash-chained JSONL log with a `verify` function.
  - `leond/policy.py`: tiers T0-T4 and the hard-deny list (no skills call it yet).
  - `leond/dock.py`: frameless, always-on-top WebView2 window; four bridge methods.
  - `leond/ui/`: the panel (HTML, CSS, JS); no framework and no build step.
  - Verified: `ruff check`, `ruff format --check`, `mypy` and `pytest` (30 tests) pass; the dock opened and answered "Say hi in three words." with "Hello, take care, goodbye."; the audit chain verified.

## In progress
- Phase 1 (brain and core loop): first half is in place, as above.

## Next 5 actions
1. Give the model tools, after a tool-call eval on the default model: one safe
   read-only tool (T0) end to end, through `policy.check` and the audit log.
2. Add the approval sheet: a T2/T3 request pauses the turn with Allow / Deny.
3. Persist the conversation (SQLite) instead of keeping it in memory.
4. Add a global hotkey to summon the dock (`Win+Alt+L`), for example through a
   small Win32 `RegisterHotKey` wrapper.
5. Add a tray icon and a one-click kill switch that stops the worker thread.

## Blocked
- Nothing blocking. A better model would help answer quality: the 4B heretic
  model is installed but needs about 180 s for 8 tokens on this CPU (D-009).

## Known gaps
- The dock has no tray icon, no global hotkey and no settings UI yet.
- Conversation history is in memory only; closing the dock forgets it.
- The policy engine is not yet wired to any action, because there are none.

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
