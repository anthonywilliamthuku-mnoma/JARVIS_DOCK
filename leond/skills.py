"""What LEON can actually do on this PC.

Every skill declares a permission tier and a JSON schema. The model may only
ask for a skill by name; core decides whether it runs, asks the user first, or
refuses. Handlers never raise for bad input: they return a sentence the model
can read, so a failed call becomes an explanation rather than a crash.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leond import attention, facts, inbox, screen
from leond.policy import Tier

MAX_OUTPUT = 1800


class SkillError(Exception):
    """A skill could not run; the message is shown to the model."""


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str
    parameters: dict[str, Any]
    tier: Tier
    run: Callable[[dict[str, Any]], str]


def _arg(args: dict[str, Any], key: str, default: str = "") -> str:
    value = args.get(key, default)
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return default
    return str(value).strip()


# -- read-only skills ------------------------------------------------------


def _local_time(args: dict[str, Any]) -> str:
    return facts.local_time()


def _local_place(args: dict[str, Any]) -> str:
    return facts.local_place()


def _system_report(args: dict[str, Any]) -> str:
    return facts.system_report()


# -- actions ---------------------------------------------------------------

# Only these names can be launched. Anything else is refused, so a model slip
# cannot become "start this executable".
APPS: dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "command prompt": "cmd.exe",
    "cmd": "cmd.exe",
    "snipping tool": "snippingtool.exe",
    "settings": "ms-settings:",
    "control panel": "control.exe",
}


def _open_app(args: dict[str, Any]) -> str:
    wanted = _arg(args, "app").lower()
    if not wanted:
        raise SkillError("no application name was given")
    target = APPS.get(wanted)
    if target is None:
        match = next((value for key, value in APPS.items() if wanted in key), "")
        target = match
    if not target:
        allowed = ", ".join(sorted({key for key in APPS if key != "calc"}))
        raise SkillError(f"'{wanted}' is not on the launch list. Allowed: {allowed}")
    try:
        if target.endswith(":"):
            os.startfile(target)  # noqa: S606 - fixed Windows protocol target
        else:
            subprocess.Popen([target])  # noqa: S603 - value comes from APPS only
    except OSError as exc:
        raise SkillError(f"could not start {wanted}: {exc.strerror or exc}") from exc
    return f"Started {wanted}."


def notes_dir() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home()))) / "LEON" / "notes"
    return base


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned[:48] or "note"


def _write_note(args: dict[str, Any]) -> str:
    body = _arg(args, "text")
    if not body:
        raise SkillError("there was nothing to write")
    title = _arg(args, "title") or body.splitlines()[0][:40]
    target = notes_dir() / f"{_slug(title)}.md"
    try:
        notes_dir().mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
    except OSError as exc:
        raise SkillError(f"could not write the note: {exc}") from exc
    return f"Saved the note to {target}."


def _run_powershell(args: dict[str, Any]) -> str:
    command = _arg(args, "command")
    if not command:
        raise SkillError("no command was given")
    try:
        completed = subprocess.run(  # noqa: S603 - reviewed by the user first
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SkillError("the command took longer than 60 seconds and was stopped") from exc
    except OSError as exc:
        raise SkillError(f"PowerShell could not start: {exc}") from exc

    output = (completed.stdout or "").strip()
    error = (completed.stderr or "").strip()
    if len(output) > MAX_OUTPUT:
        output = output[:MAX_OUTPUT] + "\n…(cut)"
    if len(error) > MAX_OUTPUT:
        error = error[:MAX_OUTPUT] + "\n…(cut)"
    if completed.returncode != 0 and not output:
        return f"PowerShell exited {completed.returncode}. {error or 'No output.'}"
    return output or error or f"PowerShell exited {completed.returncode} with no output."


def _look_at_screen(args: dict[str, Any]) -> str:
    found = screen.text()
    if not found.get("ok"):
        raise SkillError(str(found.get("error") or "the screen could not be read"))
    window = str(found.get("window") or "the front window")
    body = str(found.get("text") or "")
    if not body:
        return f"I looked at {window}. {found.get('message') or 'Nothing readable was there.'}"
    return f"Text in {window}:\n{body[:1800]}"


def _save_screenshot(args: dict[str, Any]) -> str:
    shot = screen.capture()
    if not shot.get("ok"):
        raise SkillError(str(shot.get("error") or "the screen could not be copied"))
    return f"Saved the screen to {shot['path']} ({shot['width']}x{shot['height']})."


def _type_text(args: dict[str, Any]) -> str:
    body = _arg(args, "text")
    if not body:
        raise SkillError("there was nothing to type")
    result = screen.type_text(body)
    if not result.get("ok"):
        raise SkillError(str(result.get("error") or "typing failed"))
    return f"Typed {result.get('typed', 0)} characters into the window in front."


def _click_at(args: dict[str, Any]) -> str:
    try:
        x = int(float(_arg(args, "x")))
        y = int(float(_arg(args, "y")))
    except ValueError:
        raise SkillError("x and y must be numbers") from None
    result = screen.click(x, y)
    if not result.get("ok"):
        raise SkillError(str(result.get("error") or "the click did not land"))
    return f"Clicked at {x},{y}."


def _get_attention(args: dict[str, Any]) -> str:
    return attention.ask(_arg(args, "reason")).sentence()


def _held_files(args: dict[str, Any]) -> str:
    return inbox.describe()


SKILLS: dict[str, Skill] = {
    "local_time": Skill(
        name="local_time",
        description="The current local date, time, UTC offset and time zone of this PC.",
        parameters={"type": "object", "properties": {}, "required": []},
        tier=Tier.OBSERVE,
        run=_local_time,
    ),
    "local_place": Skill(
        name="local_place",
        description="The country and time zone of this PC, as Windows reports them.",
        parameters={"type": "object", "properties": {}, "required": []},
        tier=Tier.OBSERVE,
        run=_local_place,
    ),
    "system_report": Skill(
        name="system_report",
        description="Operating system, processor count, memory use and free disk space.",
        parameters={"type": "object", "properties": {}, "required": []},
        tier=Tier.OBSERVE,
        run=_system_report,
    ),
    "open_app": Skill(
        name="open_app",
        description="Open an application on this PC, for example Notepad or Calculator.",
        parameters={
            "type": "object",
            "properties": {
                "app": {"type": "string", "description": "Application to open, e.g. notepad"}
            },
            "required": ["app"],
        },
        tier=Tier.ACT,
        run=_open_app,
    ),
    "write_note": Skill(
        name="write_note",
        description="Save a note as a Markdown file in LEON's notes folder.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short title for the file"},
                "text": {"type": "string", "description": "Body of the note"},
            },
            "required": ["text"],
        },
        tier=Tier.ACT,
        run=_write_note,
    ),
    "look_at_screen": Skill(
        name="look_at_screen",
        description=(
            "Read what is on this PC's screen: the front window's title and the words and "
            "controls it shows. Use it when the user refers to what they can see."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        tier=Tier.OBSERVE,
        run=_look_at_screen,
    ),
    "list_held_files": Skill(
        name="list_held_files",
        description="List the files sitting in the dock's inbox folder.",
        parameters={"type": "object", "properties": {}, "required": []},
        tier=Tier.OBSERVE,
        run=_held_files,
    ),
    "save_screenshot": Skill(
        name="save_screenshot",
        description="Save a picture of the whole screen into LEON's own folder.",
        parameters={"type": "object", "properties": {}, "required": []},
        tier=Tier.ACT,
        run=_save_screenshot,
    ),
    "get_attention": Skill(
        name="get_attention",
        description=(
            "Pause whatever is playing, ping, and glow the island until the user answers. "
            "Use it only when the user asked to be interrupted."
        ),
        parameters={
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "One short line to show"}},
            "required": [],
        },
        tier=Tier.ACT,
        run=_get_attention,
    ),
    "type_text": Skill(
        name="type_text",
        description="Type text into the window that is in front, as the keyboard would.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Text to type"}},
            "required": ["text"],
        },
        tier=Tier.SENSITIVE,
        run=_type_text,
    ),
    "click_at": Skill(
        name="click_at",
        description="Left-click once at a screen position, x from the left and y from the top.",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "number", "description": "Pixels from the left edge"},
                "y": {"type": "number", "description": "Pixels from the top edge"},
            },
            "required": ["x", "y"],
        },
        tier=Tier.SENSITIVE,
        run=_click_at,
    ),
    "run_powershell": Skill(
        name="run_powershell",
        description=(
            "Run a PowerShell command on this PC and return its output. Use only when the "
            "user clearly asked for something that needs it."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to run"},
                "why": {"type": "string", "description": "One line shown to the user"},
            },
            "required": ["command"],
        },
        tier=Tier.SENSITIVE,
        run=_run_powershell,
    ),
}


def schema_list() -> list[dict[str, Any]]:
    """Tool definitions in the OpenAI ``tools`` format."""
    return [
        {
            "type": "function",
            "function": {
                "name": skill.name,
                "description": skill.description,
                "parameters": skill.parameters,
            },
        }
        for skill in SKILLS.values()
    ]


def parse_args(raw: str) -> dict[str, Any]:
    """Turn the model's argument string into a dict, tolerating junk."""
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise SkillError("the arguments were not valid JSON") from None
    if not isinstance(value, dict):
        raise SkillError("the arguments must be a JSON object")
    return value


def execute(name: str, args: dict[str, Any]) -> str:
    skill = SKILLS.get(name)
    if skill is None:
        return f"There is no skill called '{name}'."
    started = time.perf_counter()
    try:
        result = skill.run(args)
    except SkillError as exc:
        return f"{name} failed: {exc}"
    elapsed = time.perf_counter() - started
    if elapsed > 1.0:
        return f"{result} (took {elapsed:.1f}s)"
    return result


def describe(name: str, args: dict[str, Any]) -> str:
    """One line for the approval card: exactly what will happen."""
    if name == "run_powershell":
        return _arg(args, "command") or "(no command)"
    if name == "open_app":
        return f"open {_arg(args, 'app')}"
    if name == "write_note":
        first_line = (_arg(args, "text").splitlines() or ["note"])[0][:40]
        return f"save note: {_arg(args, 'title') or first_line}"
    if name == "type_text":
        return f"type: {_arg(args, 'text')[:60]}"
    if name == "click_at":
        return f"click at {_arg(args, 'x')},{_arg(args, 'y')}"
    if name == "get_attention":
        return f"ping you: {_arg(args, 'reason') or 'may I have a moment?'}"
    if name == "save_screenshot":
        return "save a picture of the screen"
    return name


def subject(name: str, args: dict[str, Any]) -> str:
    """The text the policy engine inspects for a call.

    Only the risky part of the arguments is included, so a note about "deleting
    old files" does not look like a delete command.
    """
    for key in ("command", "app"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return f"{name} {value.strip()}"
    return name
