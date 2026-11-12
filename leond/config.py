"""Configuration for the LEON dock.

Defaults are chosen so the dock runs on an ordinary PC: a small local model,
a short context, and no network access beyond the loopback model endpoint.

Precedence: built-in defaults < ``%APPDATA%/LEON/config.toml`` < environment.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

DEFAULT_ENDPOINT = "http://127.0.0.1:11434/v1"
DEFAULT_MODEL = "qwen2.5-0.5b-heretic:latest"

# Names are fixed so users can copy them from config.toml into the environment.
ENV_ENDPOINT = "LEON_ENDPOINT"
ENV_MODEL = "LEON_MODEL"
ENV_CONTEXT = "LEON_CONTEXT"
ENV_TEMPERATURE = "LEON_TEMPERATURE"


def config_dir() -> Path:
    """Directory holding LEON's user files."""
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".config"
    return root / "LEON"


def config_path() -> Path:
    return config_dir() / "config.toml"


@dataclass(frozen=True, slots=True)
class Config:
    """Everything the dock needs to start."""

    endpoint: str = DEFAULT_ENDPOINT
    model: str = DEFAULT_MODEL
    context: int = 2048
    temperature: float = 0.4
    timeout_s: float = 300.0
    on_top: bool = True
    speak_replies: bool = True
    width: int = 420
    height: int = 620
    accent: str = "#7C5CFF"
    system_prompt: str = (
        "You are LEON, a calm, concise assistant running locally on this PC. "
        "Answer in the user's language. Prefer short, useful replies. "
        "You can act on this PC through your skills. When the user asks you to do "
        "something on the machine, call the matching skill directly instead of explaining "
        "how the user could do it. Ask for approval only through the skill's own Allow "
        "card, never by asking in chat first."
    )

    @property
    def chat_url(self) -> str:
        return f"{self.endpoint.rstrip('/')}/chat/completions"

    def with_model(self, model: str) -> Config:
        return replace(self, model=model)


class ConfigError(Exception):
    """Raised when a configuration value is unusable."""


def _read_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc


def _as_int(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ConfigError(f"{name} must be an integer, not a boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    raise ConfigError(f"{name} must be an integer, got {value!r}")


def _as_float(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise ConfigError(f"{name} must be a number, not a boolean")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            pass
    raise ConfigError(f"{name} must be a number, got {value!r}")


def load(path: Path | None = None) -> Config:
    """Load configuration, applying file values then environment overrides."""
    cfg = Config()
    raw = _read_toml(path if path is not None else config_path())

    model = raw.get("model")
    if isinstance(model, str) and model.strip():
        cfg = replace(cfg, model=model.strip())

    endpoint = raw.get("endpoint")
    if isinstance(endpoint, str) and endpoint.strip():
        cfg = replace(cfg, endpoint=endpoint.strip())

    on_top = raw.get("on_top")
    if isinstance(on_top, bool):
        cfg = replace(cfg, on_top=on_top)

    speak_replies = raw.get("speak_replies")
    if isinstance(speak_replies, bool):
        cfg = replace(cfg, speak_replies=speak_replies)

    if "context" in raw:
        cfg = replace(cfg, context=_as_int(raw["context"], "context"))
    if "temperature" in raw:
        cfg = replace(cfg, temperature=_as_float(raw["temperature"], "temperature"))

    accent = raw.get("accent")
    if isinstance(accent, str) and accent.strip():
        cfg = replace(cfg, accent=accent.strip())

    env_model = os.environ.get(ENV_MODEL, "").strip()
    if env_model:
        cfg = replace(cfg, model=env_model)

    env_endpoint = os.environ.get(ENV_ENDPOINT, "").strip()
    if env_endpoint:
        cfg = replace(cfg, endpoint=env_endpoint)

    env_context = os.environ.get(ENV_CONTEXT, "").strip()
    if env_context:
        cfg = replace(cfg, context=_as_int(env_context, ENV_CONTEXT))

    env_temperature = os.environ.get(ENV_TEMPERATURE, "").strip()
    if env_temperature:
        cfg = replace(cfg, temperature=_as_float(env_temperature, ENV_TEMPERATURE))

    if cfg.context < 256:
        raise ConfigError("context must be at least 256 tokens")
    return cfg


def save_template(path: Path | None = None) -> Path:
    """Write a commented config file if none exists, and return its path."""
    target = path if path is not None else config_path()
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    cfg = Config()
    target.write_text(
        "# LEON dock settings.\n"
        "# Any local OpenAI-compatible server works (Ollama, llama.cpp, LM Studio).\n"
        f'endpoint = "{cfg.endpoint}"\n'
        f'model = "{cfg.model}"\n'
        f"context = {cfg.context}\n"
        f"temperature = {cfg.temperature}\n"
        f"on_top = {'true' if cfg.on_top else 'false'}\n"
        f"speak_replies = {'true' if cfg.speak_replies else 'false'}\n"
        f'accent = "{cfg.accent}"\n',
        encoding="utf-8",
    )
    return target
