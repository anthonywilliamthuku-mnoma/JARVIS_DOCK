"""Append-only, hash-chained audit log.

Each line holds a JSON object with the hash of the previous line, so removing
or editing an entry breaks every hash after it. Only paths and short labels are
written here; message text and secrets are never stored.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

GENESIS = "0" * 64


@dataclass(frozen=True, slots=True)
class AuditEntry:
    ts: float
    kind: str
    detail: str
    outcome: str


def _digest(prev: str, payload: dict[str, object]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(prev.encode() + blob).hexdigest()


class AuditLog:
    """Writes chained entries to a JSON Lines file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._prev = self._last_hash()

    @property
    def path(self) -> Path:
        return self._path

    def _last_hash(self) -> str:
        try:
            with self._path.open("rb") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                if size == 0:
                    return GENESIS
                block = min(size, 8192)
                handle.seek(size - block)
                tail = handle.read().decode("utf-8", "replace").splitlines()
        except FileNotFoundError:
            return GENESIS
        for line in reversed(tail):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            value = record.get("hash")
            if isinstance(value, str):
                return value
        return GENESIS

    def write(self, kind: str, detail: str, outcome: str) -> str:
        """Append one entry and return its hash."""
        entry = AuditEntry(ts=time.time(), kind=kind, detail=detail, outcome=outcome)
        payload: dict[str, object] = asdict(entry)
        payload["prev"] = self._prev
        payload["hash"] = _digest(self._prev, payload)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        self._prev = str(payload["hash"])
        return self._prev


def verify(path: Path) -> tuple[bool, str]:
    """Check an audit file's chain. Returns (ok, message)."""
    prev = GENESIS
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return True, "no audit log yet"
    except OSError as exc:
        return False, f"cannot read audit log: {exc}"

    count = 0
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return False, f"line {number} is not valid JSON"
        if not isinstance(record, dict):
            return False, f"line {number} is not an object"
        claimed = record.get("hash")
        if record.get("prev") != prev:
            return False, f"line {number} does not follow the previous hash"
        body = {key: value for key, value in record.items() if key != "hash"}
        if not isinstance(claimed, str) or _digest(prev, body) != claimed:
            return False, f"line {number} has been altered"
        prev = claimed
        count += 1
    return True, f"{count} entries verified"
