from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.cogs.base import WardenCog

log = logging.getLogger("warden.verify")

VERIFY_EMOJI = "✅"


class Verify(WardenCog):
    """Grants the Verified role when someone reacts to the rules message."""

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.user_id == self.bot.user.id:
            return
        if payload.emoji.name != VERIFY_EMOJI:
            return

        config = await self.config(payload.guild_id)
        if not config.verify_message or payload.message_id != config.verify_message:
            return
        if not config.verified_role:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role = guild.get_role(config.verified_role)
        if role is None:
            log.warning("verified role %s missing", config.verified_role)
            return

        member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.HTTPException:
                return
        if role in member.roles:
            return

        try:
            await member.add_roles(role, reason="verified via rules reaction")
        except discord.HTTPException as exc:
            log.warning("could not verify %s: %s", payload.user_id, exc.status)
            return
        log.info("verified %s (%s)", member, member.id)
        try:
            await member.send(
                f"You're verified in **{guild.name}** — all channels are unlocked."
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    # on_reaction_remove intentionally not handled: verification is one-time


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Verify(bot))
