from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs.base import WardenCog
from bot.services import filters as F
from bot.services.enforcement import send_case_log

log = logging.getLogger("warden.raid")

MAX_TRACK_SECONDS = 600.0
ALERT_COOLDOWN = 60.0


class Raid(WardenCog):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)
        self._joins: dict[int, deque[float]] = defaultdict(deque)
        self._alerted_at: dict[int, float] = {}

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        now = time.time()
        bucket = self._joins[member.guild.id]
        bucket.append(now)
        while bucket and now - bucket[0] > MAX_TRACK_SECONDS:
            bucket.popleft()

        config = await self.config(member.guild.id)
        raid = {**F.DEFAULT_RAID, **(config.filters.get("raid") or {})}
        hit = F.within_window(list(bucket), int(raid["count"]), float(raid["window"]))
        if not hit:
            return
        if now - self._alerted_at.get(member.guild.id, 0.0) < ALERT_COOLDOWN:
            return
        self._alerted_at[member.guild.id] = now

        embed = discord.Embed(
            title="Possible raid",
            description=(
                f"{raid['count']} joins within {raid['window']}s. "
                f"Run `/lockdown on` to freeze non-mod chat."
            ),
            color=discord.Color.red(),
        )
        await send_case_log(config, member.guild, embed)

    @app_commands.command(description="Freeze chat for non-mods and raise verification level")
    @app_commands.describe(mode="on = lockdown, off = restore")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    async def lockdown(self, interaction: discord.Interaction, mode: str) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        assert interaction.guild is not None
        config = await self.config(interaction.guild_id)

        if mode == "on":
            if config.lockdown:
                await interaction.response.send_message(
                    "Lockdown is already active.", ephemeral=True
                )
                return
            config.filters["prev_verification"] = interaction.guild.verification_level.value
            config.lockdown = True
            new_level = discord.VerificationLevel.high
            action = "engaged"
        else:
            if not config.lockdown:
                await interaction.response.send_message(
                    "No lockdown to lift.", ephemeral=True
                )
                return
            prev = config.filters.pop("prev_verification", 0)
            config.lockdown = False
            new_level = discord.VerificationLevel(prev)
            action = "lifted"

        try:
            await interaction.guild.edit(
                verification_level=new_level, reason=f"warden lockdown {action}"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I need the **Manage Server** permission to change verification level.",
                ephemeral=True,
            )
            return
        await self.bot.db.set_config(config)

        embed = discord.Embed(
            title=f"Lockdown {action}",
            description=f"By {interaction.user.mention} · non-mod messages are deleted"
            if mode == "on"
            else f"By {interaction.user.mention} · verification restored",
            color=discord.Color.red() if mode == "on" else discord.Color.green(),
        )
        await send_case_log(config, interaction.guild, embed)
        await interaction.response.send_message(
            f"Lockdown **{action}**.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Raid(bot))
