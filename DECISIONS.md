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
- **Status:** Superseded by D-007. The Claude SDK is no longer the provider.

## D-007: LLM provider is Heretic (hosted, OpenAI-compatible)
- **Decision:** The brain uses a local model, `xtools-at/DeepSeek-V4-Pro-Qwen3.5-4B-UNCENSORED-heretic` (Apache-2.0, Hugging Face), served by a local OpenAI-compatible server (vLLM, SGLang, llama.cpp or Ollama). The provider sits behind an `LLMProvider` interface whose base URL and model name come from config, so a hosted endpoint can replace it later.
- **Model facts (from the model card):** Qwen3.5-4B fine-tune, about 5B params, BF16 safetensors. GGUF quantizations exist (about 2.8 GB at Q4_K_M, 4.5 GB at Q8_0). Refusals 5/100 versus 99/100 for the original. The card says coding and tool-use generalization have not been established, and that it is an experimental community model.
- **Supersedes:** D-005 and D-006. The user has no Anthropic account.
- **Unverified:** Tool calling is the main risk. LEON's skills depend on it, and the card says it is not established for this checkpoint. Phase 1 must include a tool-call eval on this model before the brain is built on it. Hardware (GPU/VRAM) and the chosen runtime are not yet confirmed.
- **Risk:** Heretic is an abliterated model with its refusals removed, so it will not reliably refuse harmful or injected instructions. LEON's safety must come from the policy engine, the hard-deny list, approvals and the audit log, not from the model. Treat all model output and tool results as untrusted (spec §4).
- **Not to confuse with:** The open-source `heretic-llm` tool (pip, AGPL-3.0) is a separate project for removing refusals from models you host yourself. It is not used here.

## D-008: The dock is our own window, not a Tauri build
- **Decision:** The dock is one Python process: `leond` hosts a frameless, always-on-top WebView2 window through `pywebview` and serves plain HTML/CSS/JS from `leond/ui/`. The page talks to Python in-process through the WebView bridge (`window.pywebview.api`), with four methods: `hello`, `send`, `stop`, `close`.
- **Alternatives:** Tauri 2 + React (the original Phase 5 plan), Electron, a browser tab on a loopback server.
- **Reason:** Performance on the target hardware. Tauri needs a Rust toolchain and a long first build, and Electron ships a whole Chromium; both are heavy on this 8 GB, HDD-only machine. WebView2 is already present on Windows and adds no package of its own. Vanilla JS with no bundler means no Node dependency, no build step and near-instant startup. Animations use only opacity and transform, and there is no `backdrop-filter`, so the panel stays smooth on integrated graphics.
- **Trade-off:** No global hotkey yet (pywebview has no API for one) and the UI is hand-written rather than componentised. The elaborated Tauri plan in `ARCHITECTURE.md` is superseded for the dock.
- **Safety note:** An in-process bridge is tighter than a WebSocket: no port is opened, so there is no token to leak and nothing on the network to reach. If a separate daemon is needed later, `DockApi` is the seam to put a transport behind.

## D-009: Default model is the small local one
- **Decision:** Ship with `qwen2.5-0.5b-heretic:latest` as the default, configurable in `%APPDATA%/LEON/config.toml` or via `LEON_MODEL`.
- **Reason:** Measured on the target PC (Intel HD Graphics 520, 8 GB RAM, CPU only): the chosen 4B heretic model (`Q4_K_M`, 3.1 GB on disk) worked but produced 8 tokens in about 180 seconds, which makes conversation impractical. The 0.5B model answers in seconds. The 4B stays installed so it can be selected when more memory or better hardware is available.
- **Consequence:** Answer quality on the default model is modest. Its tool calling was verified on 2026-11-10: asked for free disk space it called `system_report` and answered with the real figure, so tools are handed to it.

## D-010: Ground every turn in live facts instead of trusting the model
- **Decision:** Each request sends a system prompt containing a block read from Windows at call time: local time with UTC offset, time zone, region country code, OS build, processor count, memory use and free disk space (`leond/facts.py`).
- **Alternatives:** Let the model answer from training data, or add a lookup skill for every fact.
- **Reason:** A 0.5B model cannot know today's date, this machine's time zone or how full the disk is. Injection makes "what time is it" correct on any model, and it costs one short string per request. The lookup skills (`local_time`, `local_place`, `system_report`) stay for when the model wants the detail explicitly.
- **Note:** The region reports what Windows is set to, which may not match the time zone (this PC reports country code `US` with `E. Africa Standard Time`). Facts are reported as-is, never corrected silently.

## D-011: Skills run through policy and approval, never straight from the model
- **Decision:** `leond/skills.py` defines each skill with a permission tier and a JSON schema. `leond/agent.py` checks `policy.check` before anything runs; T2 and above raise an Allow / Deny card in the island and wait up to 120 seconds, and an unanswered card is a denial.
- **Reason:** The model is untrusted input (spec §4). It may only name a skill and supply arguments; core decides. `open_app` launches only from a fixed allowlist, so a slip cannot become "start this executable". Only the risky argument is shown to the policy engine, so a note about "deleting old files" is not mistaken for a delete command.
- **Bounded:** At most three model steps per turn, so a tool loop cannot run away.
- **Audited:** Every call and decision is written to the audit log by skill name and outcome, never with its arguments.

## D-012: The dock is a Nook-style capsule, 223 x 43, pinned to the top
- **Decision:** The shell is recreated from Nook 0.4.2's shell, at the user's size: a transparent **223 x 43** glass capsule at the top centre, flush with the screen edge (x centred, y = 0). Opening it grows the same window downwards to 520 x 560; the pill stays as the panel's header. Python owns the native geometry through `geometry()`, a pure function so the placement is unit-tested.
- **Reason:** The user asked for Nook's dock recreated for LEON at exactly these dimensions. The capsule is small enough to sit above other windows all day, and because both states share one centre line and one top edge the window only ever grows downwards.
- **Borrowed from Nook 0.4.2 (MIT, "The Nook contributors"):** the capsule-to-panel shell, the 120 ms hover debounce and 250 ms leave grace, click-to-pin, the 70% charcoal glass gradient with a 1 px rim and top highlight, and the clock in the pill. The implementation is LEON's own HTML/CSS/JS over the pywebview bridge; no Nook code is vendored, and no Rust/OpenGL toolchain is introduced.
- **Deliberate differences:** Nook composes real acrylic blur through `Windows.UI.Composition` and draws a squircle with a superellipse exponent of 4. LEON uses a semi-transparent window over the desktop with a plain CSS radius instead, because a blur pass and per-frame shape work are the wrong trade on an HD 520. Nook's spring resize is faked here by the window resizing once and the content unfurling with a short overshoot curve.
- **Trade-off:** A transparent window is composited by the desktop, slightly dearer than an opaque one; `transparent=False` is the fallback if a machine misbehaves. There is still no global summon hotkey, because pywebview exposes no API for one (a Win32 `RegisterHotKey` wrapper is the next step).
