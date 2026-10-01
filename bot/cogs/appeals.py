from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs.base import WardenCog
from bot.core.models import Appeal, GuildConfig

log = logging.getLogger("warden.appeals")


class AppealModal(discord.ui.Modal, title="Submit your appeal"):
    statement = discord.ui.TextInput(
        label="Why should the punishment be reconsidered?",
        style=discord.TextStyle.paragraph,
        max_length=2000,
    )

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        db = self.bot.db
        config = await db.find_by_appeal_guild(interaction.guild_id)
        if config is None:
            await interaction.response.send_message(
                "This server isn't configured for appeals.", ephemeral=True
            )
            return
        if config.log_channel is None:
            await interaction.response.send_message(
                "Appeals aren't ready — no mod log channel configured.", ephemeral=True
            )
            return

        try:
            appeal_id = await db.create_appeal(
                config.guild_id, interaction.user.id, str(self.statement.value)
            )
        except ValueError:
            existing = await db.pending_appeal(config.guild_id, interaction.user.id)
            await interaction.response.send_message(
                f"You already have pending appeal #{existing}.", ephemeral=True
            )
            return

        target = self.bot.get_guild(config.guild_id)
        if target is None:
            log.error("main guild %s not in cache", config.guild_id)
            await interaction.response.send_message(
                "Could not reach the moderation team. Try again later.", ephemeral=True
            )
            return
        posted = await self._post_queue(target, config, interaction.user, appeal_id)
        if not posted:
            await interaction.response.send_message(
                "Could not reach the moderation team. Try again later.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"Appeal #{appeal_id} submitted. You'll get a DM when a decision is made.",
            ephemeral=True,
        )

    async def _post_queue(
        self,
        target: discord.Guild,
        config: GuildConfig,
        user: discord.User,
        appeal_id: int,
    ) -> bool:
        channel = target.get_channel(config.log_channel)
        if not isinstance(channel, discord.TextChannel):
            return False
        embed = discord.Embed(
            title=f"Appeal #{appeal_id}",
            description=self.statement.value,
            color=discord.Color.orange(),
        )
        embed.add_field(name="Appellant", value=f"{user.mention} (`{user.id}`)")
        embed.set_footer(text="/appeal approve or /appeal deny")
        try:
            message = await channel.send(embed=embed)
        except discord.HTTPException as exc:
            log.warning("appeal queue post failed: %s", exc.status)
            return False
        try:
            thread = await message.create_thread(name=f"appeal #{appeal_id} — {user}")
            await self.bot.db.set_appeal_thread(config.guild_id, appeal_id, thread.id)
        except discord.HTTPException:
            pass  # queue embed alone is enough
        return True


class Appeals(WardenCog):
    appeal = app_commands.Group(
        name="appeal", description="Ban appeal workflow"
    )

    @appeal.command(
        name="submit", description="Appeal a punishment (works from the appeal server)"
    )
    async def submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AppealModal(self.bot))

    @appeal.command(name="approve", description="Approve an appeal and lift the ban")
    @app_commands.describe(appeal_id="Appeal number from the mod log")
    async def approve(self, interaction: discord.Interaction, appeal_id: int) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        assert interaction.guild is not None
        appeal = await self.bot.db.get_appeal(interaction.guild_id, appeal_id)
        if appeal is None:
            await interaction.response.send_message(
                f"No appeal #{appeal_id} in this server.", ephemeral=True
            )
            return
        if appeal.status != "pending":
            await interaction.response.send_message(
                f"Appeal #{appeal_id} is already {appeal.status}.", ephemeral=True
            )
            return

        note = "ban lifted"
        try:
            await interaction.guild.unban(
                discord.Object(id=appeal.user_id),
                reason=f"warden appeal #{appeal_id} approved",
            )
        except discord.NotFound:
            note = "no active ban to lift"
        except discord.Forbidden:
            await interaction.response.send_message(
                "I need the **Ban Members** permission to lift the ban.", ephemeral=True
            )
            return

        await self._resolve(interaction, appeal, "approved", note, discord.Color.green())

    @appeal.command(name="deny", description="Deny an appeal")
    @app_commands.describe(
        appeal_id="Appeal number from the mod log", reason="Shown to the appellant"
    )
    async def deny(
        self, interaction: discord.Interaction, appeal_id: int, reason: str = "No."
    ) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        assert interaction.guild is not None
        appeal = await self.bot.db.get_appeal(interaction.guild_id, appeal_id)
        if appeal is None:
            await interaction.response.send_message(
                f"No appeal #{appeal_id} in this server.", ephemeral=True
            )
            return
        if appeal.status != "pending":
            await interaction.response.send_message(
                f"Appeal #{appeal_id} is already {appeal.status}.", ephemeral=True
            )
            return

        await self._resolve(interaction, appeal, "denied", reason, discord.Color.red())

    async def _resolve(
        self,
        interaction: discord.Interaction,
        appeal: Appeal,
        status: str,
        note: str,
        color: discord.Color,
    ) -> None:
        ok = await self.bot.db.resolve_appeal(
            interaction.guild_id, appeal.id, status, interaction.user.id
        )
        if not ok:
            await interaction.response.send_message(
                "Someone just resolved that appeal.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"Appeal #{appeal.id} {status.upper()}",
            description=note,
            color=color,
        )
        embed.add_field(name="Appellant", value=f"<@{appeal.user_id}> (`{appeal.user_id}`)")
        embed.add_field(name="Decided by", value=interaction.user.mention)
        config = await self.config(interaction.guild_id)
        await self._post_resolution(config, interaction.guild, appeal, embed)
        await self._dm_appellant(appeal, status, note)
        await interaction.response.send_message(
            f"Appeal #{appeal.id} **{status}**. {note}", ephemeral=True
        )

    async def _post_resolution(
        self,
        config: GuildConfig,
        guild: discord.Guild,
        appeal: Appeal,
        embed: discord.Embed,
    ) -> None:
        if config.log_channel is not None:
            channel = guild.get_channel(config.log_channel)
            if isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException as exc:
                    log.warning("resolution post failed: %s", exc.status)
        if appeal.thread_id is not None:
            try:
                thread = await guild.fetch_channel(appeal.thread_id)
                await thread.send(embed=embed)
                await thread.edit(archived=True, locked=True)
            except (discord.NotFound, discord.HTTPException):
                pass

    async def _dm_appellant(self, appeal: Appeal, status: str, note: str) -> None:
        try:
            user = await self.bot.fetch_user(appeal.user_id)
            await user.send(f"Your appeal #{appeal.id} was **{status}**: {note}")
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Appeals(bot))
