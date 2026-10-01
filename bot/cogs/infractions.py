from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs.base import WardenCog
from bot.services.enforcement import case_embed, record, send_case_log


class Infractions(WardenCog):
    @staticmethod
    def _hierarchy_blocked(actor: discord.Member, target: discord.Member) -> str | None:
        if target.id == actor.guild.me.id:
            return "I won't act on myself."
        if target.id == actor.id:
            return "You can't warn yourself."
        if target.top_role >= actor.top_role and not actor.guild_permissions.administrator:
            return "Their top role is not below yours."
        return None

    @app_commands.command(description="Record an infraction; escalates automatically when due")
    @app_commands.describe(user="Member to warn", reason="Why")
    async def warn(
        self, interaction: discord.Interaction, user: discord.Member, reason: str
    ) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        assert isinstance(interaction.user, discord.Member)
        block = self._hierarchy_blocked(interaction.user, user)
        if block:
            await interaction.response.send_message(block, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        config = await self.config(interaction.guild_id)
        result = await record(
            self.bot.db,
            config,
            guild_id=interaction.guild_id,
            user_id=user.id,
            mod_id=interaction.user.id,
            reason=reason,
            member=user,
        )
        embed = case_embed(result.infraction, result.action, result.active_count, result.note)
        await send_case_log(config, interaction.guild, embed)

        line = f"Case #{result.infraction.id} recorded for {user.mention}"
        line += f" ({result.active_count} active)."
        if result.action != "none":
            line += f"\nEscalation applied: **{result.action}**."
        if result.note:
            line += f"\n{result.note}"
        await interaction.followup.send(line, ephemeral=True)

    @app_commands.command(description="Remove a strike from a member's record")
    @app_commands.describe(case_id="Case number from the mod log")
    async def unwarn(self, interaction: discord.Interaction, case_id: int) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        infraction = await self.bot.db.get_infraction(interaction.guild_id, case_id)
        if infraction is None:
            await interaction.response.send_message(f"No case #{case_id} here.", ephemeral=True)
            return
        if not infraction.active:
            await interaction.response.send_message(
                f"Case #{case_id} is already inactive.", ephemeral=True
            )
            return
        await self.bot.db.deactivate_case(interaction.guild_id, case_id)
        embed = discord.Embed(
            title=f"Case #{case_id} overturned",
            description=f"<@{infraction.user_id}> — strike removed by {interaction.user.mention}",
            color=discord.Color.green(),
        )
        config = await self.config(interaction.guild_id)
        await send_case_log(config, interaction.guild, embed)
        active = await self.bot.db.active_infraction_count(
            interaction.guild_id, infraction.user_id
        )
        await interaction.response.send_message(
            f"Case #{case_id} removed. <@{infraction.user_id}> now has {active} active.",
            ephemeral=True,
        )

    @app_commands.command(description="Show a member's infraction history")
    @app_commands.describe(user="Member to inspect")
    async def history(self, interaction: discord.Interaction, user: discord.Member) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        rows = await self.bot.db.history(interaction.guild_id, user.id)
        embed = discord.Embed(title=f"Record for {user}", color=discord.Color.blurple())
        if not rows:
            embed.description = "Clean record."
        else:
            lines = []
            for row in rows[:15]:
                state = "" if row.active else " ~~struck~~"
                lines.append(f"**#{row.id}** [{row.source}] {row.reason[:80]}{state}")
            active = sum(1 for row in rows if row.active)
            embed.description = f"{active} active of {len(rows)} total.\n" + "\n".join(lines)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Infractions(bot))
