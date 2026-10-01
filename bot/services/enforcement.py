"""Shared enforcement: record an infraction, escalate, build case-log embeds."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

import discord

from bot.core.db import Database
from bot.core.models import GuildConfig, Infraction
from bot.services.escalation import evaluate

log = logging.getLogger("warden.enforcement")

TIMEOUT_DURATION = timedelta(hours=24)

ACTION_COLOR = {
    "none": discord.Color.blurple(),
    "timeout": discord.Color.gold(),
    "kick": discord.Color.orange(),
    "ban": discord.Color.red(),
}


@dataclass
class EnforceResult:
    infraction: Infraction
    active_count: int
    action: str
    note: str | None


async def apply_action(member: discord.Member, action: str, case_id: int) -> str | None:
    """Execute the escalation action; returns a failure note instead of raising."""
    reason = f"warden case #{case_id}"
    try:
        if action == "timeout":
            await member.timeout(until=TIMEOUT_DURATION, reason=reason)
        elif action == "kick":
            await member.kick(reason=reason)
        elif action == "ban":
            await member.ban(reason=reason)
    except discord.Forbidden:
        log.warning("missing permissions to %s %s", action, member.id)
        return f"action `{action}` failed — I lack permissions or hierarchy"
    except discord.HTTPException as exc:
        log.warning("failed to %s %s: %s", action, member.id, exc)
        return f"action `{action}` failed ({exc.status})"
    return None


async def record(
    db: Database,
    config: GuildConfig,
    *,
    guild_id: int,
    user_id: int,
    mod_id: int,
    reason: str,
    source: str = "manual",
    member: discord.Member | None = None,
) -> EnforceResult:
    """Add an infraction, count it, evaluate escalation, apply if due."""
    case_id = await db.add_infraction(guild_id, user_id, mod_id, reason, source)
    infraction = await db.get_infraction(guild_id, case_id)
    assert infraction is not None
    active = await db.active_infraction_count(guild_id, user_id)
    action = evaluate(active, config.escalation)
    note: str | None = None
    if action != "none":
        if member is None:
            raise ValueError("member is required when escalation action triggers")
        note = await apply_action(member, action, case_id)
    return EnforceResult(infraction=infraction, active_count=active, action=action, note=note)


def case_embed(
    infraction: Infraction, action: str, active_count: int, note: str | None
) -> discord.Embed:
    if action != "none":
        title = f"Case #{infraction.id} · {action.upper()}"
    else:
        title = f"Case #{infraction.id}"
    embed = discord.Embed(title=title, color=ACTION_COLOR[action])
    embed.add_field(name="User", value=f"<@{infraction.user_id}> (`{infraction.user_id}`)")
    moderator = (
        "Automod" if infraction.mod_id == 0 else f"<@{infraction.mod_id}> (`{infraction.mod_id}`)"
    )
    embed.add_field(name="Moderator", value=moderator)
    embed.add_field(name="Source", value=infraction.source, inline=True)
    embed.add_field(name="Active infractions", value=str(active_count), inline=True)
    embed.add_field(name="Reason", value=infraction.reason or "—", inline=False)
    if note:
        embed.add_field(name="Note", value=note, inline=False)
    embed.set_footer(text="unwarn reverses the strike, not the punishment")
    return embed


async def send_case_log(config: GuildConfig, guild: discord.Guild, embed: discord.Embed) -> None:
    if config.log_channel is None:
        return
    channel = guild.get_channel(config.log_channel)
    if isinstance(channel, discord.TextChannel):
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as exc:
            log.warning("case log send failed: %s", exc.status)
