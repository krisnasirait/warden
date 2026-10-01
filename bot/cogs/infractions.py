from __future__ import annotations

import logging
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.models import GuildConfig, Infraction
from bot.core.permissions import has_mod_role
from bot.services.escalation import evaluate

log = logging.getLogger("warden.infractions")

TIMEOUT_DURATION = timedelta(hours=24)

ACTION_COLOR = {
    "none": discord.Color.blurple(),
    "timeout": discord.Color.gold(),
    "kick": discord.Color.orange(),
    "ban": discord.Color.red(),
}


class Infractions(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _config(self, guild_id: int) -> GuildConfig:
        config = await self.bot.db.get_config(guild_id)
        if config is None:
            config = GuildConfig(guild_id=guild_id)
            await self.bot.db.set_config(config)
        return config

    async def _deny_if_not_mod(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Guild only.", ephemeral=True)
            return True
        config = await self._config(interaction.guild_id)
        role_ids = [r.id for r in interaction.user.roles]
        is_admin = interaction.user.guild_permissions.administrator
        if has_mod_role(role_ids, config.mod_role, is_admin):
            return False
        await interaction.response.send_message(
            "You need the moderator role to do that.", ephemeral=True
        )
        return True

    @staticmethod
    def _hierarchy_blocked(actor: discord.Member, target: discord.Member) -> str | None:
        if target.id == actor.guild.me.id:
            return "I won't act on myself."
        if target.id == actor.id:
            return "You can't warn yourself."
        if target.top_role >= actor.top_role and not actor.guild_permissions.administrator:
            return "Their top role is not below yours."
        return None

    async def _apply_action(self, member: discord.Member, action: str, case_id: int) -> str | None:
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

    def _case_embed(
        self,
        config: GuildConfig,
        infraction: Infraction,
        action: str,
        active_count: int,
        applied_note: str | None,
    ) -> discord.Embed:
        if action != "none":
            title = f"Case #{infraction.id} · {action.upper()}"
        else:
            title = f"Case #{infraction.id}"
        embed = discord.Embed(title=title, color=ACTION_COLOR[action])
        embed.add_field(name="User", value=f"<@{infraction.user_id}> (`{infraction.user_id}`)")
        embed.add_field(name="Moderator", value=f"<@{infraction.mod_id}>")
        embed.add_field(name="Source", value=infraction.source, inline=True)
        embed.add_field(name="Active infractions", value=str(active_count), inline=True)
        embed.add_field(name="Reason", value=infraction.reason or "—", inline=False)
        if applied_note:
            embed.add_field(name="Note", value=applied_note, inline=False)
        embed.set_footer(text="unwarn reverses the strike, not the punishment")
        return embed

    async def _send_case_log(
        self, config: GuildConfig, guild: discord.Guild, embed: discord.Embed
    ) -> None:
        if config.log_channel is None:
            return
        channel = guild.get_channel(config.log_channel)
        if isinstance(channel, discord.TextChannel):
            await channel.send(embed=embed)

    @app_commands.command(description="Record an infraction; escalates automatically when due")
    @app_commands.describe(user="Member to warn", reason="Why")
    async def warn(
        self, interaction: discord.Interaction, user: discord.Member, reason: str
    ) -> None:
        if await self._deny_if_not_mod(interaction):
            return
        assert isinstance(interaction.user, discord.Member)
        block = self._hierarchy_blocked(interaction.user, user)
        if block:
            await interaction.response.send_message(block, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        config = await self._config(interaction.guild_id)
        case_id = await self.bot.db.add_infraction(
            interaction.guild_id, user.id, interaction.user.id, reason
        )
        infraction = await self.bot.db.get_infraction(interaction.guild_id, case_id)
        assert infraction is not None

        active = await self.bot.db.active_infraction_count(interaction.guild_id, user.id)
        action = evaluate(active, config.escalation)
        applied_note = None
        if action != "none":
            applied_note = await self._apply_action(user, action, case_id)

        embed = self._case_embed(config, infraction, action, active, applied_note)
        await self._send_case_log(config, interaction.guild, embed)

        line = f"Case #{case_id} recorded for {user.mention} ({active} active)."
        if action != "none":
            line += f"\nEscalation applied: **{action}**."
        if applied_note:
            line += f"\n{applied_note}"
        await interaction.followup.send(line, ephemeral=True)

    @app_commands.command(description="Remove a strike from a member's record")
    @app_commands.describe(case_id="Case number from the mod log")
    async def unwarn(self, interaction: discord.Interaction, case_id: int) -> None:
        if await self._deny_if_not_mod(interaction):
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
        config = await self._config(interaction.guild_id)
        await self._send_case_log(config, interaction.guild, embed)
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
        if await self._deny_if_not_mod(interaction):
            return
        rows = await self.bot.db.history(interaction.guild_id, user.id)
        embed = discord.Embed(
            title=f"Record for {user}",
            color=discord.Color.blurple(),
        )
        if not rows:
            embed.description = "Clean record."
        else:
            lines = []
            for row in rows[:15]:
                state = "" if row.active else " ~~struck~~"
                lines.append(
                    f"**#{row.id}** [{row.source}] {row.reason[:80]}{state}"
                )
            active = sum(1 for row in rows if row.active)
            embed.description = f"{active} active of {len(rows)} total.\n" + "\n".join(lines)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Infractions(bot))
