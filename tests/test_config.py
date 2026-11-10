from pathlib import Path

import pytest

from leond import config


def test_defaults_point_at_local_ollama() -> None:
    cfg = config.load(Path("does-not-exist.toml"))
    assert cfg.endpoint == config.DEFAULT_ENDPOINT
    assert cfg.model == config.DEFAULT_MODEL
    assert cfg.chat_url == f"{config.DEFAULT_ENDPOINT}/chat/completions"


def test_file_values_override_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('model = "tiny"\ncontext = 1024\ntemperature = 0.1\n', encoding="utf-8")
    cfg = config.load(path)
    assert cfg.model == "tiny"
    assert cfg.context == 1024
    assert cfg.temperature == pytest.approx(0.1)


def test_environment_beats_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "config.toml"
    path.write_text('model = "from-file"\n', encoding="utf-8")
    monkeypatch.setenv(config.ENV_MODEL, "from-env")
    assert config.load(path).model == "from-env"


def test_context_must_be_usable(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("context = 64\n", encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.load(path)


def test_broken_toml_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("model = [unclosed\n", encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.load(path)


def test_template_is_written_once(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "config.toml"
    config.save_template(path)
    assert path.exists()
    path.write_text("model = 'kept'\n", encoding="utf-8")
    config.save_template(path)
    assert "kept" in path.read_text(encoding="utf-8")
