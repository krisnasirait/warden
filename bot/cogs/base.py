from __future__ import annotations

import discord
from discord.ext import commands

from bot.core.models import GuildConfig
from bot.core.permissions import has_mod_role


class WardenCog(commands.Cog):
    """Shared config fetch + staff checks for all warden cogs."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def config(self, guild_id: int) -> GuildConfig:
        config = await self.bot.db.get_config(guild_id)
        if config is None:
            config = GuildConfig(guild_id=guild_id)
            await self.bot.db.set_config(config)
        return config

    def is_staff(self, member: discord.Member, config: GuildConfig) -> bool:
        role_ids = [r.id for r in member.roles]
        return has_mod_role(
            role_ids, config.mod_role, member.guild_permissions.administrator
        )

    async def deny_if_not_mod(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Guild only.", ephemeral=True)
            return True
        config = await self.config(interaction.guild_id)
        if self.is_staff(interaction.user, config):
            return False
        await interaction.response.send_message(
            "You need the moderator role to do that.", ephemeral=True
        )
        return True
