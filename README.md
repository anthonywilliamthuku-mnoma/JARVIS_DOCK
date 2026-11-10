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

## The island

The dock is a pill pinned to the top centre of the screen. Collapsed it shows
what LEON is doing and nothing more. Click it (or the chevron) and the same
window grows downwards into the conversation; **Esc** closes it again, and
dragging the pill moves it.

## What it does today

- **Real facts.** Every turn carries a live block read from Windows: local time
  and UTC offset, time zone, region, operating system, memory use and free disk
  space. Ask "what time is it" and the answer comes from the PC, not the model.
- **Real tasks.** The model can call the skills below, and each call is checked
  by the policy engine first.
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

T0 skills run immediately. T2 actions raise an approval card in the island
showing the exact command; an unanswered card is a refusal, and the hard-deny
list in `leond/policy.py` refuses destructive commands outright with no
override.

## Layout

```
leond/
  config.py     settings: TOML file plus environment overrides
  facts.py      live Windows facts (time, place, system, disk)
  brain.py      streaming client for local OpenAI-compatible servers, with tools
  skills.py     what LEON can do, each with a tier and a JSON schema
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

Phase 0 (foundations) is complete. Phase 1 (brain and core loop) is in
progress: the model client, config, policy skeleton and audit log exist, and
the dock is a working vertical slice. Skills, approval sheets and the elevated
helper are still to come. See `PROGRESS.md` and `DECISIONS.md`.
