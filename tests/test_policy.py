import pytest

from leond.policy import Tier, check


@pytest.mark.parametrize(
    "action",
    [
        "format d:",
        "diskpart",
        "bcdedit /set safeboot minimal",
        "powershell -EncodedCommand ZQBjAGgAbwA=",
        "vssadmin delete shadows /all",
        "net user hacker Pass123 /add",
        "reg delete HKLM\\Software\\Foo /f",
    ],
)
def test_destructive_actions_are_never_allowed(action: str) -> None:
    decision = check(action, Tier.ADMIN)
    assert not decision.allowed
    assert decision.tier is Tier.NEVER
    assert decision.reason


def test_reading_files_needs_no_confirmation() -> None:
    decision = check("read C:/Users/me/notes.txt", Tier.OBSERVE)
    assert decision.allowed
    assert not decision.ask


def test_deleting_asks_first() -> None:
    decision = check("delete the old screenshots", Tier.ACT)
    assert decision.allowed
    assert decision.ask
    assert decision.tier is Tier.SENSITIVE


def test_admin_work_asks_for_uac() -> None:
    decision = check("install a driver", Tier.ACT)
    assert decision.allowed
    assert decision.ask
    assert decision.tier is Tier.ADMIN


def test_never_tier_is_refused() -> None:
    decision = check("anything at all", Tier.NEVER)
    assert not decision.allowed


def test_empty_action_is_refused() -> None:
    assert not check("   ", Tier.OBSERVE).allowed
