from datetime import timedelta

from bot.main import _humanize_uptime


def test_uptime_minutes_only():
    assert _humanize_uptime(timedelta(minutes=5)) == "5m"


def test_uptime_zero():
    assert _humanize_uptime(timedelta(0)) == "0m"


def test_uptime_hours_and_minutes():
    assert _humanize_uptime(timedelta(hours=2, minutes=30)) == "2h 30m"


def test_uptime_full():
    assert _humanize_uptime(timedelta(days=3, hours=4, minutes=5)) == "3d 4h 5m"


def test_uptime_whole_days_drop_zero_minutes():
    assert _humanize_uptime(timedelta(days=3)) == "3d"


def test_uptime_exact_day_boundary():
    assert _humanize_uptime(timedelta(days=1, hours=1)) == "1d 1h"
