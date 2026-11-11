"""One turn of LEON: listen, maybe act, then answer.

The loop is deliberately short. The model may ask for at most a few skills per
turn, each request is checked by the policy engine first, and anything that
changes the PC waits for a real click from the user.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from leond import facts, skills
from leond.audit import AuditLog
from leond.brain import Brain, BrainError, Calls, Delta, Message, ToolCall, trim
from leond.config import Config
from leond.policy import check

MAX_STEPS = 3


@dataclass(slots=True)
class Hooks:
    """How the agent reaches the dock."""

    on_text: Callable[[str], None]
    on_state: Callable[[str], None]
    ask: Callable[[str, str, str], bool]


def system_prompt(cfg: Config) -> str:
    return f"{cfg.system_prompt}\n\n{facts.snapshot()}"


class Agent:
    def __init__(self, cfg: Config, brain: Brain, audit: AuditLog) -> None:
        self._cfg = cfg
        self._brain = brain
        self._audit = audit

    def answer(
        self,
        history: list[Message],
        text: str,
        hooks: Hooks,
        cancel: threading.Event,
    ) -> str:
        """Run one turn, streaming text through ``hooks``, and return the reply."""
        history.append(Message("user", text))
        schema = skills.schema_list()
        spoken: list[str] = []
        said = 0

        for step in range(MAX_STEPS):
            if cancel.is_set():
                break
            if step > 0:
                hooks.on_state("thinking…")
            # Only what this step said belongs in this step's history entry:
            # re-sending earlier sentences makes a small model repeat itself.
            said = len(spoken)
            calls = self._step(history, schema, hooks, cancel, spoken)
            if not calls:
                break
            self._act(history, calls, hooks, spoken[said:], step)
        else:
            hooks.on_state("that needed more steps than I take")

        reply = "".join(spoken).strip()
        # The tool checkpoints already hold the earlier steps, so the closing
        # entry carries only the words the last step added.
        closing = "".join(spoken[said:]).strip()
        if closing:
            history.append(Message("assistant", closing))
        return reply

    def _step(
        self,
        history: list[Message],
        schema: list[dict[str, object]],
        hooks: Hooks,
        cancel: threading.Event,
        spoken: list[str],
    ) -> tuple[ToolCall, ...]:
        """One model call. Returns the tool calls, if any."""
        view = trim(history, self._cfg.context)
        try:
            events = self._brain.stream(
                view,
                cancel=cancel,
                tools=schema,
                system=system_prompt(self._cfg),
            )
            for event in events:
                if isinstance(event, Delta):
                    spoken.append(event.text)
                    hooks.on_text(event.text)
                elif isinstance(event, Calls):
                    return event.calls
        except BrainError as exc:
            raise BrainError(str(exc)) from exc
        return ()

    def _act(
        self,
        history: list[Message],
        calls: tuple[ToolCall, ...],
        hooks: Hooks,
        spoken: list[str],
        step: int,
    ) -> None:
        parsed: list[Message] = []
        request: list[dict[str, object]] = []
        for call in calls:
            request.append(call.as_payload())
            parsed.append(self._run_one(call.name, call.arguments, call.id, hooks, step))
        history.append(Message("assistant", "".join(spoken), tool_calls=tuple(request)))
        history.extend(parsed)

    def _run_one(self, name: str, raw: str, call_id: str, hooks: Hooks, step: int = 0) -> Message:
        """Check, maybe ask, then run one skill."""
        try:
            args = skills.parse_args(raw)
        except skills.SkillError as exc:
            return Message("tool", f"{name} failed: {exc}", tool_call_id=call_id)

        skill = skills.SKILLS.get(name)
        if skill is None:
            return Message("tool", f"There is no skill called '{name}'.", tool_call_id=call_id)

        decision = check(skills.subject(name, args), skill.tier)
        if not decision.allowed:
            self._audit.write("skill", name, "refused")
            return Message(
                "tool",
                f"Refused by policy: {decision.reason}. Tell the user plainly that you cannot.",
                tool_call_id=call_id,
            )

        if decision.ask:
            detail = skills.describe(name, args)
            approved = hooks.ask(name, detail, decision.reason)
            if not approved:
                self._audit.write("skill", name, "denied")
                return Message(
                    "tool",
                    "The user denied this action. Do not try again; say so briefly.",
                    tool_call_id=call_id,
                )

        hooks.on_state(f"{name}… {step + 1}/{MAX_STEPS}")
        result = skills.execute(name, args)
        self._audit.write(
            "skill", name, "ok" if not result.startswith(f"{name} failed") else "error"
        )
        return Message("tool", result, tool_call_id=call_id)
