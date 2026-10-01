import pytest

from bot.services.escalation import Action, evaluate, validate_thresholds


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, "none"),
        (1, "none"),
        (2, "none"),
        (3, "timeout"),
        (4, "timeout"),
        (5, "kick"),
        (6, "kick"),
        (7, "ban"),
        (100, "ban"),
    ],
)
def test_default_thresholds(count, expected):
    assert evaluate(count) == expected


def test_custom_thresholds():
    thresholds = {1: "timeout", 2: "ban"}
    assert evaluate(1, thresholds) == "timeout"
    assert evaluate(2, thresholds) == "ban"


def test_most_severe_wins_when_multiple_pass():
    thresholds = {1: "timeout", 2: "kick", 3: "ban"}
    assert evaluate(3, thresholds) == "ban"


def test_empty_thresholds_disarm():
    assert evaluate(50, {}) == "none"


def test_unknown_action_ignored():
    thresholds = {1: "yeet", 2: "ban"}
    assert evaluate(1, thresholds) == "none"
    assert evaluate(2, thresholds) == "ban"


def test_negative_count_is_none():
    assert evaluate(-1) == "none"


def test_action_severity_ordering():
    assert Action.NONE < Action.TIMEOUT < Action.KICK < Action.BAN


def test_validate_thresholds_accepts_valid():
    assert validate_thresholds({3: "timeout", 7: "ban"}) == {3: "timeout", 7: "ban"}


def test_validate_thresholds_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        validate_thresholds({})


@pytest.mark.parametrize(
    ("bad", "match"),
    [({0: "timeout"}, "positive"), ({-2: "kick"}, "positive"), ({2: "nuke"}, "unknown")],
)
def test_validate_thresholds_rejects_garbage(bad, match):
    with pytest.raises(ValueError, match=match):
        validate_thresholds(bad)
