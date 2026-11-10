"""The brain: a streaming client for any local OpenAI-compatible server.

Ollama, llama.cpp's server and LM Studio all expose ``/v1/chat/completions``,
so one small stdlib client covers every runtime a user is likely to have. The
stream yields text as it arrives and, if the model asked for tools instead of
speaking, a final :class:`Calls` event.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from leond.config import Config

DONE = "[DONE]"


class BrainError(Exception):
    """A reply could not be produced, with a message fit for the UI."""


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str
    tool_calls: tuple[dict[str, Any], ...] = ()
    tool_call_id: str | None = None

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = list(self.tool_calls)
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        return payload


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


@dataclass(frozen=True, slots=True)
class Delta:
    """A piece of the reply, ready to be shown."""

    text: str


@dataclass(frozen=True, slots=True)
class Calls:
    """The model wants tools run before it answers."""

    calls: tuple[ToolCall, ...]


Event = Delta | Calls


def _describe(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", "replace")
    except OSError:
        body = ""
    detail = ""
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            message = parsed.get("error")
            if isinstance(message, str):
                detail = message
            elif isinstance(message, dict):
                inner = message.get("message")
                detail = inner if isinstance(inner, str) else ""
    except json.JSONDecodeError:
        detail = body.strip()[:200]
    if exc.code == 404:
        return f"the model is not installed on the server ({detail or 'not found'})"
    if exc.code == 400:
        return f"the server rejected the request ({detail or 'bad request'})"
    return f"the server answered {exc.code} ({detail or exc.reason})"


@dataclass
class _PendingCall:
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class _Collector:
    """Accumulates streamed tool-call fragments, which arrive in pieces."""

    order: list[int] = field(default_factory=list)
    parts: dict[int, _PendingCall] = field(default_factory=dict)

    def add(self, entry: object) -> None:
        if not isinstance(entry, dict):
            return
        index = entry.get("index")
        slot = index if isinstance(index, int) else 0
        pending = self.parts.setdefault(slot, _PendingCall())
        if slot not in self.order:
            self.order.append(slot)
        call_id = entry.get("id")
        if isinstance(call_id, str) and call_id:
            pending.id = call_id
        function = entry.get("function")
        if not isinstance(function, dict):
            return
        name = function.get("name")
        if isinstance(name, str) and name:
            pending.name += name
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            pending.arguments += arguments

    def calls(self) -> tuple[ToolCall, ...]:
        made: list[ToolCall] = []
        for position, slot in enumerate(self.order):
            pending = self.parts[slot]
            if not pending.name:
                continue
            made.append(
                ToolCall(
                    id=pending.id or f"call_{position}",
                    name=pending.name,
                    arguments=pending.arguments or "{}",
                )
            )
        return tuple(made)


class Brain:
    """Talks to one model at one endpoint."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg

    @property
    def config(self) -> Config:
        return self._cfg

    def _request(
        self,
        messages: list[Message],
        stream: bool,
        max_tokens: int,
        tools: list[dict[str, Any]] | None,
        system: str,
    ) -> urllib.request.Request:
        payload_messages: list[dict[str, Any]] = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(m.as_payload() for m in messages if m.role != "system")

        payload: dict[str, Any] = {
            "model": self._cfg.model,
            "messages": payload_messages,
            "stream": stream,
            "max_tokens": max_tokens,
            "temperature": self._cfg.temperature,
        }
        if tools:
            payload["tools"] = tools
        body = json.dumps(payload).encode()
        return urllib.request.Request(
            self._cfg.chat_url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )

    def stream(
        self,
        messages: list[Message],
        cancel: threading.Event | None = None,
        max_tokens: int = 512,
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> Iterator[Event]:
        """Yield reply text, then a :class:`Calls` event if tools were requested.

        Setting ``cancel`` stops early; the connection is closed so the server
        frees the slot instead of finishing the sentence.
        """
        request = self._request(
            messages, True, max_tokens, tools, self._cfg.system_prompt if system is None else system
        )
        try:
            response = urllib.request.urlopen(request, timeout=self._cfg.timeout_s)
        except urllib.error.HTTPError as exc:
            raise BrainError(_describe(exc)) from exc
        except urllib.error.URLError as exc:
            raise BrainError(
                f"cannot reach the model server at {self._cfg.endpoint} ({exc.reason})"
            ) from exc
        except TimeoutError as exc:
            raise BrainError("the model server took too long to answer") from exc

        collector = _Collector()
        try:
            for raw in response:
                if cancel is not None and cancel.is_set():
                    break
                line = raw.decode("utf-8", "replace").strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == DONE:
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                text = _delta_text(chunk)
                if text:
                    yield Delta(text)
                for entry in _chunk_tool_calls(chunk):
                    collector.add(entry)
        except TimeoutError as exc:
            raise BrainError("the model stopped responding") from exc
        finally:
            response.close()

        calls = collector.calls()
        if calls:
            yield Calls(calls)

    def reply(self, messages: list[Message], max_tokens: int = 512) -> str:
        """Collect a whole reply, for scripts and tests."""
        events = self.stream(messages, max_tokens=max_tokens)
        return "".join(event.text for event in events if isinstance(event, Delta)).strip()


def _delta_text(chunk: object) -> str:
    if not isinstance(chunk, dict):
        return ""
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    for key in ("delta", "message"):
        holder = first.get(key)
        if isinstance(holder, dict):
            content = holder.get("content")
            if isinstance(content, str):
                return content
    return ""


def _chunk_tool_calls(chunk: object) -> list[object]:
    if not isinstance(chunk, dict):
        return []
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return []
    first = choices[0]
    if not isinstance(first, dict):
        return []
    for key in ("delta", "message"):
        holder = first.get(key)
        if isinstance(holder, dict):
            calls = holder.get("tool_calls")
            if isinstance(calls, list):
                return calls
    return []


def trim(messages: list[Message], context: int, reserve: int = 512) -> list[Message]:
    """Keep recent turns that plausibly fit, so small models do not choke."""
    budget = max(256, context - reserve) * 3  # about three characters per token
    kept: list[Message] = []
    used = 0
    for message in reversed(messages):
        cost = len(message.content) + 8
        if used + cost > budget and kept:
            break
        kept.append(message)
        used += cost
    kept.reverse()
    return kept
