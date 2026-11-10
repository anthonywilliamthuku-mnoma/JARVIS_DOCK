from pathlib import Path

import pytest

from leond import skills
from leond.policy import Tier


def test_every_skill_is_described_for_the_model() -> None:
    schema = skills.schema_list()
    names = {item["function"]["name"] for item in schema if isinstance(item["function"], dict)}
    assert names == set(skills.SKILLS)
    assert "local_time" in names


def test_reading_skills_are_observe_only() -> None:
    assert skills.SKILLS["local_time"].tier is Tier.OBSERVE
    assert skills.SKILLS["system_report"].tier is Tier.OBSERVE


def test_run_powershell_needs_a_confirmation() -> None:
    assert skills.SKILLS["run_powershell"].tier is Tier.SENSITIVE


def test_arguments_must_be_an_object() -> None:
    with pytest.raises(skills.SkillError):
        skills.parse_args("[1, 2]")
    with pytest.raises(skills.SkillError):
        skills.parse_args("{broken")
    assert skills.parse_args("") == {}


def test_unknown_skill_is_reported_not_raised() -> None:
    assert "no skill" in skills.execute("format_everything", {})


def test_unknown_app_is_refused() -> None:
    result = skills.execute("open_app", {"app": "definitely-not-installed"})
    assert "not on the launch list" in result


def test_notes_are_written_as_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    result = skills.execute("write_note", {"title": "Shopping List", "text": "milk\nbread"})
    saved = tmp_path / "LEON" / "notes" / "shopping-list.md"
    assert saved.exists()
    assert "milk" in saved.read_text(encoding="utf-8")
    assert "Saved the note" in result


def test_subject_only_includes_the_risky_argument() -> None:
    assert skills.subject("run_powershell", {"command": "Get-Date"}) == "run_powershell Get-Date"
    note = {"title": "delete old files", "text": "thinking about deleting things"}
    assert skills.subject("write_note", note) == "write_note"


def test_describe_shows_exactly_what_will_run() -> None:
    assert skills.describe("run_powershell", {"command": "Get-Process"}) == "Get-Process"
    assert "notepad" in skills.describe("open_app", {"app": "notepad"})
