"""The brain: a streaming client for any local OpenAI-compatible server.

Ollama, llama.cpp's server and LM Studio all expose ``/v1/chat/completions``,
so one small stdlib client covers every runtime a user is likely to have. No
SDK is needed, which keeps startup fast and the dependency list short.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass

from leond.config import Config

DONE = "[DONE]"


class BrainError(Exception):
    """A reply could not be produced, with a message fit for the UI."""


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str

    def as_payload(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


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


class Brain:
    """Talks to one model at one endpoint."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg

    @property
    def config(self) -> Config:
        return self._cfg

    def _request(
        self, messages: list[Message], stream: bool, max_tokens: int
    ) -> urllib.request.Request:
        payload_messages: list[dict[str, str]] = []
        if self._cfg.system_prompt:
            payload_messages.append({"role": "system", "content": self._cfg.system_prompt})
        payload_messages.extend(m.as_payload() for m in messages if m.role != "system")

        payload: dict[str, object] = {
            "model": self._cfg.model,
            "messages": payload_messages,
            "stream": stream,
            "max_tokens": max_tokens,
            "temperature": self._cfg.temperature,
        }
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
    ) -> Iterator[str]:
        """Yield reply text as it arrives.

        The caller may stop early by setting ``cancel``; the connection is then
        closed so the server frees the slot instead of finishing the sentence.
        """
        request = self._request(messages, stream=True, max_tokens=max_tokens)
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

        try:
            for raw in response:
                if cancel is not None and cancel.is_set():
                    break
                line = raw.decode("utf-8", "replace").strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
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
                    yield text
        except TimeoutError as exc:
            raise BrainError("the model stopped responding") from exc
        finally:
            response.close()

    def reply(self, messages: list[Message], max_tokens: int = 512) -> str:
        """Collect a whole reply, for scripts and tests."""
        return "".join(self.stream(messages, max_tokens=max_tokens)).strip()


def _delta_text(chunk: object) -> str:
    if not isinstance(chunk, dict):
        return ""
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    delta = first.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        return content if isinstance(content, str) else ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        return content if isinstance(content, str) else ""
    return ""


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
