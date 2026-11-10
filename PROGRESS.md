# Progress

Single source of truth for LEON. Re-read at the start of every session.

## Done
- **Phase 0 (foundations):** project skeleton, `pyproject.toml` (uv, ruff, mypy strict, pytest), CI workflow, `ARCHITECTURE.md`, `DECISIONS.md`, `SKILLS.md`, this file.
  - Verified locally: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest` all pass.

## In progress
- Phase 1 (brain and core loop) not started.

## Next 5 actions
1. Verify current Claude model names and capabilities at https://docs.claude.com (D-005).
2. Choose raw Messages API vs Claude Agent SDK and log it (D-006).
3. Build the `LLMProvider` interface and the Anthropic implementation with streaming, retries with backoff, and model fallback.
4. Add config loading (TOML, layered, schema-validated) and structured logging with secret redaction.
5. Add `leon chat` (streaming CLI) with a demo tool, reporting tokens and cost per task.

## Blocked
- Nothing blocking. Phase 1 needs an Anthropic API key from the user, supplied as an env var or in Windows Credential Manager. Never commit it.

## Known gaps
- The repo's `README.md` is the original placeholder. It gets install, quick start, architecture and safety docs in Phase 8.

## How to run tests
```
uv sync --locked --python 3.12
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```
