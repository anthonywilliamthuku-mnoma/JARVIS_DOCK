# Decisions

Format: decision, alternatives considered, reason. Newest entries go at the bottom.

## D-001: Python 3.12 + uv for the core project
- **Decision:** Python `>=3.12,<3.13`, managed with `uv`, lockfile `uv.lock` committed.
- **Alternatives:** Poetry, pip-tools, plain pip with requirements.txt.
- **Reason:** Matches the spec's Python 3.12 core. uv is fast and locks reproducibly, and CI uses `uv sync --locked`.

## D-002: Lint, format and types
- **Decision:** ruff for lint and format, mypy in strict mode, pytest for tests.
- **Reason:** Standard tooling with one config in `pyproject.toml`. Strict types match the spec's "typed" requirement.

## D-003: CI on GitHub Actions
- **Decision:** One job runs ruff check, ruff format check, mypy and pytest on Python 3.12.
- **Reason:** The repo is hosted on GitHub. One job keeps feedback fast for Phase 0.

## D-004: Package layout
- **Decision:** `leond/` is the core package at the repository root. Tests live in `tests/`. Skills go in `skills/` (Phase 2). The dock goes in `dock/` (Phase 5).
- **Reason:** Keeps the layout flat. Matches the spec's `skills/<name>/` structure.

## D-005: Model defaults (to verify before Phase 1)
- **Decision:** Anthropic Claude via the official SDK, with `brain`, `worker` and `fast` roles set in config. Spec defaults are `claude-opus-5-5`, `claude-sonnet-5-5` and `claude-haiku-5-5`.
- **Open:** The model names and their capabilities (tool use, streaming, caching, token limits) must be checked against https://docs.claude.com before the brain is coded. Not verified yet.
- **Reason:** The spec requires verification first. Model IDs stay in config, not code, so they can change without a code change.

## D-006: Raw Messages API vs Claude Agent SDK
- **Status:** Open. Decide in Phase 1 after reading the current docs. The choice will be logged here with the reason.
