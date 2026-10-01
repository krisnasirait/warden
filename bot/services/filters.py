"""Automod filters — pure functions over message and join streams. No Discord."""

from __future__ import annotations

import re
from urllib.parse import urlparse

DEFAULT_RATE = {"count": 5, "window": 5.0}
DEFAULT_RAID = {"count": 5, "window": 60.0}
DEFAULT_LINKS = {
    "block_invites": True,
    "block_raw_ips": True,
    "block_all_links": False,
    "allowlist": [],
}

INVITE_RE = re.compile(r"(?:discord\.gg|discord(?:app)?\.com/invite)/\S+", re.I)
IPV4_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)


def within_window(timestamps: list[float], count: int, window: float) -> bool:
    """True when `count` events fall inside `window` seconds."""
    if count < 1:
        return False
    ts = sorted(timestamps, reverse=True)
    if len(ts) < count:
        return False
    if count == 1:
        return True
    for i in range(len(ts) - count + 1):
        if ts[i] - ts[i + count - 1] <= window:
            return True
    return False


def compile_pattern(pattern: str) -> re.Pattern[str]:
    """Validate a user-supplied word filter regex; raises re.error if broken."""
    return re.compile(pattern, re.IGNORECASE)


def word_hit(content: str, patterns: list[str]) -> str | None:
    """Return the first pattern that matches, skipping invalid regexes."""
    for pattern in patterns:
        try:
            if re.search(pattern, content, re.IGNORECASE):
                return pattern
        except re.error:
            continue
    return None


def link_hit(
    content: str,
    *,
    block_invites: bool = True,
    block_raw_ips: bool = True,
    block_all_links: bool = False,
    allowlist: list[str] | None = None,
) -> str | None:
    """Return the rule name that fired, or None if the content is clean."""
    allowed = {d.lower().removeprefix("www.") for d in (allowlist or [])}

    if block_invites:
        for match in INVITE_RE.finditer(content):
            domain = match.group(0).split("/")[0].lower().removeprefix("www.")
            if domain in allowed:
                continue
            return "invite"

    for url in URL_RE.findall(content):
        domain = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
        domain = domain.removeprefix("www.")
        if domain and domain in allowed:
            continue
        if block_all_links:
            return "link"

    if block_raw_ips and IPV4_RE.search(content):
        return "raw_ip"
    return None
