import re

import pytest

from bot.services.filters import (
    compile_pattern,
    link_hit,
    within_window,
    word_hit,
)


class TestWithinWindow:
    def test_burst_trips(self):
        # 5 messages inside 5 seconds
        ts = [100.0, 101.0, 102.0, 103.0, 104.0]
        assert within_window(ts, 5, 5.0)

    def test_slow_flow_does_not_trip(self):
        ts = [0.0, 10.0, 20.0, 30.0, 40.0]
        assert not within_window(ts, 5, 5.0)

    def test_under_count_never_trips(self):
        ts = [1.0, 2.0, 3.0]
        assert not within_window(ts, 4, 100.0)

    def test_any_burst_in_long_stream_trips(self):
        ts = [0.0, 100.0, 101.0, 102.0, 103.0]
        assert within_window(ts, 4, 5.0)

    def test_unsorted_input(self):
        ts = [104.0, 100.0, 103.0, 101.0, 102.0]
        assert within_window(ts, 5, 5.0)

    def test_count_one(self):
        assert within_window([7.0], 1, 1.0)
        assert not within_window([], 1, 1.0)

    def test_zero_count(self):
        assert not within_window([1.0, 2.0], 0, 10.0)

    def test_exact_boundary(self):
        assert within_window([0.0, 5.0], 2, 5.0)
        assert not within_window([0.0, 5.01], 2, 5.0)


class TestWordHit:
    def test_case_insensitive_match(self):
        assert word_hit("You are a IDIOT", ["idiots?"]) == "idiots?"

    def test_no_match(self):
        assert word_hit("hello world", ["badword"]) is None

    def test_invalid_pattern_skipped_not_crashing(self):
        assert word_hit("text", ["[unclosed"]) is None

    def test_invalid_then_valid(self):
        assert word_hit("spam here", ["[unclosed", "spam"]) == "spam"

    def test_compile_pattern_validates(self):
        assert compile_pattern("bad\\s+word") is not None
        with pytest.raises(re.error):
            compile_pattern("[unclosed")


class TestLinkHit:
    def test_discord_invite_blocked(self):
        assert link_hit("join discord.gg/abc123") == "invite"
        assert link_hit("https://discord.com/invite/xyz") == "invite"

    def test_normal_link_allowed_by_default(self):
        assert link_hit("see https://example.com/page") is None

    def test_raw_ip_blocked(self):
        assert link_hit("connect to 192.168.1.50 now") == "raw_ip"

    def test_block_all_links(self):
        assert link_hit("https://example.com", block_all_links=True) == "link"

    def test_allowlisted_domain_exempt(self):
        assert (
            link_hit(
                "https://www.example.com/x",
                block_all_links=True,
                allowlist=["example.com"],
            )
            is None
        )

    def test_invite_blocked_before_generic_link_rule(self):
        assert link_hit("https://discord.gg/abc", block_all_links=True) == "invite"

    def test_allowlisted_invite_domain_is_exempt(self):
        # deliberate allowlist entry wins over every rule
        assert link_hit("https://discord.gg/abc", allowlist=["discord.gg"]) is None

    def test_clean_content(self):
        assert link_hit("just talking about stuff") is None

    def test_empty_content(self):
        assert link_hit("") is None
