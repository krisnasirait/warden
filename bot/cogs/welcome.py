from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.cogs.base import WardenCog

log = logging.getLogger("warden.welcome")


class Welcome(WardenCog):
    """Posts welcome/goodbye embeds. Welcome waits for native screening."""

    @staticmethod
    def _resolve(guild: discord.Guild, configured: int | None, name: str):
        if configured:
            channel = guild.get_channel(configured)
            if isinstance(channel, discord.TextChannel):
                return channel
        for channel in guild.text_channels:
            if channel.name.lower() == name:
                return channel
        return None

    def _rules_channel_id(self, guild: discord.Guild) -> int | None:
        for channel in guild.text_channels:
            if channel.name.lower() == "rules":
                return channel.id
        return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        # native membership screening: hold the welcome until they accept the rules
        if member.pending:
            log.info("member %s awaiting screening", member.id)
            return
        await self._welcome(member)

    @commands.Cog.listener()
    async def on_member_update(self, old: discord.Member, new: discord.Member) -> None:
        if old.pending and not new.pending:
            await self._welcome(new)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        config = await self.config(member.guild.id)
        channel = self._resolve(member.guild, config.goodbye_channel, "goodbye")
        if channel is None:
            return
        embed = discord.Embed(
            title="Goodbye",
            description=f"**{member}** left the server.",
            color=discord.Color.dark_grey(),
        )
        embed.set_footer(text=f"{member.guild.member_count} members remain")
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as exc:
            log.warning("goodbye send failed: %s", exc.status)

    async def _welcome(self, member: discord.Member) -> None:
        config = await self.config(member.guild.id)
        channel = self._resolve(member.guild, config.welcome_channel, "welcome")
        if channel is None:
            return

        rules_id = self._rules_channel_id(member.guild)
        rules_line = (
            f"Head over to <#{rules_id}> first." if rules_id else "Check out the rules."
        )
        count = member.guild.member_count
        embed = discord.Embed(
            title=f"Welcome to {member.guild.name}!",
            description=f"{member.mention}, you're member **{count}**.\n\n{rules_line}",
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="Account created",
            value=f"<t:{int(member.created_at.timestamp())}:R>",
            inline=True,
        )
        embed.set_footer(text=f"Member ID {member.id}")
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as exc:
            log.warning("welcome send failed: %s", exc.status)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
