from leond import facts


def test_local_time_is_a_real_clock_reading() -> None:
    text = facts.local_time()
    assert "UTC" in text
    assert ":" in text
    assert facts.now().strftime("%Y") in text


def test_system_report_describes_this_machine() -> None:
    report = facts.system_report()
    assert "Operating system:" in report
    assert "logical processors" in report


def test_snapshot_grounds_the_prompt() -> None:
    block = facts.snapshot()
    assert "Local time:" in block
    assert "Place:" in block
    assert "System:" in block


def test_place_never_returns_empty() -> None:
    assert facts.local_place().strip()
