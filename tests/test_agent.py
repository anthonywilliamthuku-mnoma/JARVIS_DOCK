import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from leond.agent import Agent, Hooks
from leond.audit import AuditLog, verify
from leond.brain import Calls, Delta, Event, Message, ToolCall
from leond.config import Config


class FakeBrain:
    """Replays a scripted stream, and records what it was asked."""

    def __init__(self, script: list[list[Event]]) -> None:
        self._script = script
        self.calls = 0
        self.seen_tools: list[dict[str, Any]] | None = None
        self.seen_messages: list[Message] = []
        self.seen_system = ""

    def stream(
        self,
        messages: list[Message],
        cancel: threading.Event | None = None,
        max_tokens: int = 512,
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> Iterator[Event]:
        self.seen_messages = list(messages)
        self.seen_tools = tools
        self.seen_system = system or ""
        step = self._script[min(self.calls, len(self._script) - 1)]
        self.calls += 1
        yield from step


def make_hooks(approved: bool = True) -> tuple[Hooks, list[str], list[tuple[str, str, str]]]:
    spoken: list[str] = []
    asked: list[tuple[str, str, str]] = []

    def ask(name: str, detail: str, reason: str) -> bool:
        asked.append((name, detail, reason))
        return approved

    hooks = Hooks(on_text=spoken.append, on_state=lambda _text: None, ask=ask)
    return hooks, spoken, asked


def make_agent(script: list[list[Event]], tmp_path: Path) -> tuple[Agent, FakeBrain, AuditLog]:
    audit = AuditLog(tmp_path / "audit.jsonl")
    brain = FakeBrain(script)
    return Agent(Config(), brain, audit), brain, audit  # type: ignore[arg-type]


def test_plain_reply_needs_no_skill(tmp_path: Path) -> None:
    agent, brain, _ = make_agent([[Delta("Hello"), Delta(" there")]], tmp_path)
    hooks, spoken, asked = make_hooks()
    reply = agent.answer([], "hi", hooks, threading.Event())
    assert reply == "Hello there"
    assert spoken == ["Hello", " there"]
    assert asked == []
    assert brain.calls == 1


def test_prompt_carries_live_facts(tmp_path: Path) -> None:
    agent, brain, _ = make_agent([[Delta("ok")]], tmp_path)
    agent.answer([], "what time is it", make_hooks()[0], threading.Event())
    assert "Local time:" in brain.seen_system
    assert "Facts read from this PC" in brain.seen_system


def test_a_read_only_skill_runs_without_asking(tmp_path: Path) -> None:
    call = ToolCall("call_1", "local_time", "{}")
    agent, brain, audit = make_agent([[Calls((call,))], [Delta("It is late.")]], tmp_path)
    hooks, _, asked = make_hooks()
    reply = agent.answer([], "what time is it", hooks, threading.Event())

    assert reply == "It is late."
    assert asked == []
    assert brain.calls == 2
    tool_message = brain.seen_messages[-1]
    assert tool_message.role == "tool"
    assert "UTC" in tool_message.content
    ok, _ = verify(audit.path)
    assert ok


def test_a_sensitive_skill_waits_for_the_user(tmp_path: Path) -> None:
    call = ToolCall("call_1", "run_powershell", '{"command": "Get-Date"}')
    agent, _, audit = make_agent([[Calls((call,))], [Delta("Done.")]], tmp_path)
    hooks, _, asked = make_hooks(approved=True)
    agent.answer([], "what is the date", hooks, threading.Event())
    assert asked and asked[0][0] == "run_powershell"
    assert asked[0][1] == "Get-Date"
    assert "Get-Date" not in audit.path.read_text(encoding="utf-8")


def test_denying_stops_the_action(tmp_path: Path) -> None:
    call = ToolCall("call_1", "run_powershell", '{"command": "Get-Date"}')
    agent, brain, audit = make_agent([[Calls((call,))], [Delta("Understood.")]], tmp_path)
    hooks, _, _ = make_hooks(approved=False)
    reply = agent.answer([], "run something", hooks, threading.Event())
    assert reply == "Understood."
    tool_message = brain.seen_messages[-1]
    assert "denied" in tool_message.content
    assert "denied" in audit.path.read_text(encoding="utf-8")


def test_hard_denied_commands_never_reach_the_user(tmp_path: Path) -> None:
    call = ToolCall("call_1", "run_powershell", '{"command": "format d:"}')
    agent, brain, _ = make_agent([[Calls((call,))], [Delta("I cannot do that.")]], tmp_path)
    hooks, _, asked = make_hooks(approved=True)
    reply = agent.answer([], "wipe drive d", hooks, threading.Event())
    assert reply == "I cannot do that."
    assert asked == []
    assert "Refused by policy" in brain.seen_messages[-1].content


def test_broken_arguments_do_not_crash_the_turn(tmp_path: Path) -> None:
    call = ToolCall("call_1", "open_app", "{not json")
    agent, brain, _ = make_agent([[Calls((call,))], [Delta("Sorry.")]], tmp_path)
    reply = agent.answer([], "open something", make_hooks()[0], threading.Event())
    assert reply == "Sorry."
    assert "not valid JSON" in brain.seen_messages[-1].content


def test_the_loop_is_bounded(tmp_path: Path) -> None:
    call = ToolCall("call_1", "local_time", "{}")
    agent, brain, _ = make_agent([[Calls((call,))]], tmp_path)
    agent.answer([], "loop forever", make_hooks()[0], threading.Event())
    assert brain.calls == 3  # MAX_STEPS


def test_a_second_step_does_not_repeat_the_first_step_text(tmp_path: Path) -> None:
    first = ToolCall("call_1", "local_time", "{}")
    second = ToolCall("call_2", "system_report", "{}")
    agent, _, _ = make_agent(
        [
            [Delta("Let me check."), Calls((first,))],
            [Calls((second,))],
            [Delta("It is late.")],
        ],
        tmp_path,
    )
    history: list[Message] = []
    reply = agent.answer(history, "what time is it", make_hooks()[0], threading.Event())

    # The reply is everything the turn said, preamble included: the user has
    # already watched those words stream past.
    assert reply == "Let me check.It is late."
    # Each step's entry holds only what that step said, so the model is never
    # handed its own earlier sentence twice.
    assert [m.content for m in history if m.role == "assistant"] == [
        "Let me check.",
        "",
        "It is late.",
    ]


def test_history_records_both_sides(tmp_path: Path) -> None:
    agent, _, _ = make_agent([[Delta("hi back")]], tmp_path)
    history: list[Message] = []
    agent.answer(history, "hi", make_hooks()[0], threading.Event())
    assert [message.role for message in history] == ["user", "assistant"]
