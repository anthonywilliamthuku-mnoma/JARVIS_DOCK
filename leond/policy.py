"""Permission tiers and the hard-deny list.

Nothing in the dock touches the machine yet, but every future action is meant to
pass through :func:`check` first, so the tiers and refusals are defined here
rather than being scattered through the code later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum


class Tier(IntEnum):
    """How risky an action is. Higher numbers need more consent."""

    OBSERVE = 0  # read-only, automatic
    ACT = 1  # reversible, inside the user's own files
    SENSITIVE = 2  # needs a confirmation
    ADMIN = 3  # needs a confirmation and a real UAC prompt
    NEVER = 4  # refused outright, no override


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    ask: bool
    tier: Tier
    reason: str


# Patterns that are refused even if the user approves them.
_HARD_DENY: tuple[tuple[str, str], ...] = (
    (r"\bformat\s+[a-z]:", "formatting a volume destroys data"),
    (r"\bdiskpart\b", "raw disk partitioning is destructive"),
    (r"\bbcdedit\b", "boot configuration changes can stop Windows starting"),
    (r"\bvssadmin\s+delete\b", "deleting shadow copies removes recovery points"),
    (r"\bcipher\s+/w\b", "wiping free space is irreversible"),
    (r"remove-item.*-recurse.*-force.*[a-z]:\\\s*$", "mass deletion of a drive"),
    (r"\bnet\s+user\s+\w+\s+.*\/add", "creating accounts is an admin action"),
    (r"net\s+localgroup\s+administrators", "changing admin group membership"),
    (r"set-mppreference.*disablerealtimemonitoring", "disabling antivirus"),
    (r"\breg\s+delete\b.*hklm", "deleting machine-wide registry keys"),
    (r"powershell\b.*\s-(enc|encodedcommand)\b", "obfuscated commands are refused"),
    (r"\brm\s+-rf\s+/\s*$", "recursive delete of the filesystem root"),
    (r"\bdel\s+\/[sq]\s+[a-z]:\*", "mass deletion of a drive"),
    (r"disable-windowsoptionalfeature", "removing Windows components"),
    (r"shutdown\b.*\/f", "forced shutdown can lose work"),
)

_COMPILED_DENY = tuple(
    (re.compile(pattern, re.IGNORECASE), reason) for pattern, reason in _HARD_DENY
)

# Verbs that touch the machine and therefore deserve a confirmation.
_SENSITIVE = re.compile(
    r"\b(delete|remove|uninstall|overwrite|move|rename|kill|stop-service|"
    r"registry|regedit|install|download|upload|send|post|email|pay)\b",
    re.IGNORECASE,
)

_ADMIN = re.compile(
    r"\b(admin|elevat|uac|hklm|service|driver|firewall|scheduled\s+task)\b",
    re.IGNORECASE,
)


def check(action: str, tier: Tier) -> Decision:
    """Classify an action and decide whether it may run."""
    text = action.strip()
    if not text:
        return Decision(allowed=False, ask=False, tier=Tier.NEVER, reason="empty action")

    for pattern, reason in _COMPILED_DENY:
        if pattern.search(text):
            return Decision(allowed=False, ask=False, tier=Tier.NEVER, reason=reason)

    if tier is Tier.NEVER:
        return Decision(allowed=False, ask=False, tier=Tier.NEVER, reason="action is marked never")

    if tier is Tier.ADMIN or _ADMIN.search(text):
        return Decision(
            allowed=True, ask=True, tier=Tier.ADMIN, reason="needs administrator approval"
        )

    if tier is Tier.SENSITIVE or _SENSITIVE.search(text):
        return Decision(
            allowed=True, ask=True, tier=Tier.SENSITIVE, reason="changes state on this PC"
        )

    if tier is Tier.ACT:
        return Decision(
            allowed=True, ask=False, tier=Tier.ACT, reason="reversible, user-level action"
        )

    return Decision(allowed=True, ask=False, tier=Tier.OBSERVE, reason="read-only")
