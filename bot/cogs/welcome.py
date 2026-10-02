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
            title=f"See you, {member.name}",
            description=(
                f"**{member}** has left **{member.guild.name}**.\n"
                f"Thanks for the time — {member.guild.member_count} members are still here."
            ),
            color=discord.Color.dark_grey(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Member ID {member.id}")
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as exc:
            log.warning("goodbye send failed: %s", exc.status)

    async def _welcome(self, member: discord.Member) -> None:
        guild = member.guild
        config = await self.config(guild.id)
        channel = self._resolve(guild, config.welcome_channel, "welcome")
        if channel is None:
            return

        steps = []
        for name, verb in (
            ("rules", "Read the rules"),
            ("roles", "Pick your roles"),
            ("general", "Say hello"),
        ):
            target = self._resolve(guild, None, name)
            if target is not None:
                steps.append(f"• {verb} in {target.mention}")
        steps_block = "\n".join(steps) if steps else "• Make yourself at home"

        embed = discord.Embed(
            title=f"Welcome to {guild.name}, {member.name}!",
            description=(
                f"{member.mention} just walked in — member "
                f"**{guild.member_count}** of the server.\n\n"
                f"**Getting started**\n{steps_block}\n\n"
                f"Glad to have you here."
            ),
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="Account created",
            value=f"<t:{int(member.created_at.timestamp())}:R>",
            inline=True,
        )
        embed.add_field(
            name="Joined",
            value=f"<t:{int(member.joined_at.timestamp()) if member.joined_at else 0}:R>",
            inline=True,
        )
        embed.set_footer(text=f"Member ID {member.id}")
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as exc:
            log.warning("welcome send failed: %s", exc.status)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
