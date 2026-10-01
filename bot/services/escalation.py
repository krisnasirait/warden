"""Pure escalation logic — no Discord imports, fully unit-testable."""

from __future__ import annotations

from enum import IntEnum


class Action(IntEnum):
    NONE = 0
    TIMEOUT = 1
    KICK = 2
    BAN = 3


VALID_ACTIONS = {"timeout", "kick", "ban"}

DEFAULT_THRESHOLDS: dict[int, str] = {3: "timeout", 5: "kick", 7: "ban"}


def evaluate(active_count: int, thresholds: dict[int, str] | None = None) -> str:
    """Return the most severe action whose threshold is <= active_count.

    Returns "none" when nothing is triggered.
    """
    if active_count <= 0:
        return "none"
    table = thresholds if thresholds is not None else DEFAULT_THRESHOLDS
    triggered = [
        action
        for count, action in table.items()
        if active_count >= count and action in VALID_ACTIONS
    ]
    if not triggered:
        return "none"
    best = max(Action[action.upper()] for action in triggered)
    return best.name.lower()


def validate_thresholds(thresholds: dict[int, str]) -> dict[int, str]:
    """Check a user-supplied escalation table; raise ValueError on garbage."""
    if not thresholds:
        raise ValueError("escalation table must not be empty")
    cleaned: dict[int, str] = {}
    for count, action in thresholds.items():
        if not isinstance(count, int) or count < 1:
            raise ValueError(f"threshold must be a positive integer, got {count!r}")
        if action not in VALID_ACTIONS:
            raise ValueError(f"unknown action {action!r}, expected one of {sorted(VALID_ACTIONS)}")
        cleaned[count] = action
    return cleaned
