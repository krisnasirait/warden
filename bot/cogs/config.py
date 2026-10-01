from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs.base import WardenCog
from bot.services.escalation import VALID_ACTIONS, validate_thresholds
from bot.services.filters import compile_pattern

ACTION_CHOICES = [
    app_commands.Choice(name=a, value=a) for a in sorted(VALID_ACTIONS)
] + [app_commands.Choice(name="clear (remove threshold)", value="clear")]


class Config(WardenCog):
    cfg = app_commands.Group(name="config", description="Guild configuration")
    flt = app_commands.Group(name="filter", description="Word filter patterns")

    @cfg.command(name="show", description="Show current configuration")
    async def show(self, interaction: discord.Interaction) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        config = await self.config(interaction.guild_id)
        escalation = ", ".join(
            f"{n}→{a}" for n, a in sorted(config.escalation.items())
        ) or "disarmed"
        words = config.filters.get("words", [])
        embed = discord.Embed(title="Warden configuration", color=discord.Color.blurple())
        embed.add_field(
            name="Mod role",
            value=f"<@&{config.mod_role}>" if config.mod_role else "*not set*",
        )
        embed.add_field(
            name="Log channel",
            value=f"<#{config.log_channel}>" if config.log_channel else "*not set*",
        )
        embed.add_field(
            name="Appeal guild",
            value=f"`{config.appeal_guild}`" if config.appeal_guild else "*not set*",
        )
        embed.add_field(
            name="Welcome / goodbye",
            value=(
                f"{f'<#{config.welcome_channel}>' if config.welcome_channel else '*#welcome*'}"
                f" / "
                f"{f'<#{config.goodbye_channel}>' if config.goodbye_channel else '*#goodbye*'}"
            ),
        )
        embed.add_field(name="Escalation", value=escalation, inline=False)
        embed.add_field(
            name="Word filters",
            value=str(len(words)) + (" patterns" if len(words) != 1 else " pattern"),
        )
        embed.add_field(
            name="Lockdown",
            value="ENGAGED" if config.lockdown else "off",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @cfg.command(name="mod-role", description="Set the moderator role")
    async def mod_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        config = await self.config(interaction.guild_id)
        config.mod_role = role.id
        await self.bot.db.set_config(config)
        await interaction.response.send_message(
            f"Moderator role set to {role.mention}.", ephemeral=True
        )

    @cfg.command(name="log-channel", description="Set the case log channel")
    async def log_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        config = await self.config(interaction.guild_id)
        config.log_channel = channel.id
        await self.bot.db.set_config(config)
        await interaction.response.send_message(
            f"Case log set to {channel.mention}.", ephemeral=True
        )

    @cfg.command(name="escalation", description="Set or clear an escalation threshold")
    @app_commands.describe(threshold="Infraction count that triggers the action")
    @app_commands.choices(action=ACTION_CHOICES)
    async def escalation(
        self,
        interaction: discord.Interaction,
        threshold: app_commands.Range[int, 1, 100],
        action: str,
    ) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        config = await self.config(interaction.guild_id)
        if action == "clear":
            if config.escalation.pop(threshold, None) is None:
                await interaction.response.send_message(
                    f"No threshold at {threshold}.", ephemeral=True
                )
                return
        else:
            config.escalation[threshold] = action
        validate_thresholds(config.escalation)
        await self.bot.db.set_config(config)
        table = ", ".join(f"{n}→{a}" for n, a in sorted(config.escalation.items()))
        await interaction.response.send_message(
            f"Escalation: {table}", ephemeral=True
        )

    @cfg.command(name="welcome-channel", description="Set the welcome message channel")
    async def welcome_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        config = await self.config(interaction.guild_id)
        config.welcome_channel = channel.id
        await self.bot.db.set_config(config)
        await interaction.response.send_message(
            f"Welcome messages → {channel.mention}.", ephemeral=True
        )

    @cfg.command(name="goodbye-channel", description="Set the goodbye message channel")
    async def goodbye_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        config = await self.config(interaction.guild_id)
        config.goodbye_channel = channel.id
        await self.bot.db.set_config(config)
        await interaction.response.send_message(
            f"Goodbye messages → {channel.mention}.", ephemeral=True
        )

    @cfg.command(
        name="appeal-guild", description="Link this server to its appeal server"
    )
    @app_commands.describe(guild_id="ID of the server where /appeal is used")
    async def appeal_guild(self, interaction: discord.Interaction, guild_id: str) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        try:
            target_id = int(guild_id)
        except ValueError:
            await interaction.response.send_message(
                "That's not a valid server ID.", ephemeral=True
            )
            return
        if self.bot.get_guild(target_id) is None:
            await interaction.response.send_message(
                "I'm not in that server.", ephemeral=True
            )
            return
        config = await self.config(interaction.guild_id)
        config.appeal_guild = target_id
        await self.bot.db.set_config(config)
        await interaction.response.send_message(
            f"Appeals from `{target_id}` will land in this server.", ephemeral=True
        )

    @flt.command(name="show", description="Show word filters and automod rules")
    async def filter_show(self, interaction: discord.Interaction) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        config = await self.config(interaction.guild_id)
        words = config.filters.get("words", [])
        embed = discord.Embed(title="Automod filters", color=discord.Color.blurple())
        embed.add_field(name="Always on", value="rate limit · invite block · raw IP block")
        embed.add_field(
            name="Word patterns",
            value="\n".join(f"`/{p}/`" for p in words[:20]) or "*none*",
        )
        if len(words) > 20:
            embed.set_footer(text=f"+{len(words) - 20} more")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @flt.command(name="add", description="Add a word filter regex")
    @app_commands.describe(pattern="Case-insensitive regex, e.g. bad\\s+word")
    async def filter_add(self, interaction: discord.Interaction, pattern: str) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        try:
            compile_pattern(pattern)
        except re.error:
            await interaction.response.send_message(
                "Invalid regex — check your escaping.", ephemeral=True
            )
            return
        config = await self.config(interaction.guild_id)
        words = config.filters.setdefault("words", [])
        if pattern in words:
            await interaction.response.send_message(
                "That pattern already exists.", ephemeral=True
            )
            return
        words.append(pattern)
        await self.bot.db.set_config(config)
        await interaction.response.send_message(
            f"Added `/{pattern}/` ({len(words)} total).", ephemeral=True
        )

    @flt.command(name="remove", description="Remove a word filter regex")
    @app_commands.describe(pattern="The exact pattern to remove")
    async def filter_remove(self, interaction: discord.Interaction, pattern: str) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        config = await self.config(interaction.guild_id)
        words = config.filters.get("words", [])
        if pattern not in words:
            await interaction.response.send_message(
                "No such pattern.", ephemeral=True
            )
            return
        words.remove(pattern)
        await self.bot.db.set_config(config)
        await interaction.response.send_message(
            f"Removed `/{pattern}/` ({len(words)} left).", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Config(bot))
