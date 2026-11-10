import json
from pathlib import Path

from leond.audit import AuditLog, verify


def test_chain_verifies_after_writes(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.write("chat", "3 chars", "sent")
    log.write("chat", "12 tokens", "ok")
    ok, message = verify(log.path)
    assert ok, message
    assert "2 entries" in message


def test_each_entry_links_to_the_one_before(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    first = log.write("chat", "a", "sent")
    second = log.write("chat", "b", "ok")
    lines = [json.loads(line) for line in log.path.read_text().splitlines()]
    assert lines[0]["prev"] == "0" * 64
    assert lines[0]["hash"] == first
    assert lines[1]["prev"] == first
    assert lines[1]["hash"] == second


def test_edited_entry_breaks_verification(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.write("chat", "3 chars", "sent")
    log.write("chat", "9 chars", "ok")
    lines = log.path.read_text().splitlines()
    lines[0] = lines[0].replace('"3 chars"', '"9 chars"')
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, message = verify(log.path)
    assert not ok
    assert "altered" in message


def test_missing_file_is_not_an_error(tmp_path: Path) -> None:
    ok, message = verify(tmp_path / "absent.jsonl")
    assert ok
    assert "no audit log" in message


def test_new_log_continues_an_existing_chain(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    AuditLog(path).write("chat", "one", "sent")
    AuditLog(path).write("chat", "two", "ok")
    ok, _ = verify(path)
    assert ok
