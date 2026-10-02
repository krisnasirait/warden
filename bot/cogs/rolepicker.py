from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.cogs.base import WardenCog

log = logging.getLogger("warden.rolepicker")


class RolePicker(WardenCog):
    """Toggles self-assignable roles from the #roles picker message."""

    async def _picker(self, guild_id: int) -> dict | None:
        config = await self.config(guild_id)
        picker = (config.filters or {}).get("role_picker")
        if not isinstance(picker, dict) or not picker.get("message"):
            return None
        return picker

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._toggle(payload, add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        await self._toggle(payload, add=False)

    async def _toggle(self, payload: discord.RawReactionActionEvent, *, add: bool) -> None:
        if payload.guild_id is None or payload.user_id == self.bot.user.id:
            return
        picker = await self._picker(payload.guild_id)
        if payload.message_id != picker["message"]:
            return

        role_id = (picker.get("roles") or {}).get(payload.emoji.name)
        if not role_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role = guild.get_role(role_id)
        if role is None:
            log.warning("picker role %s missing", role_id)
            return

        member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.HTTPException:
                return

        has = role in member.roles
        if add and has:
            return
        if not add and not has:
            return

        try:
            if add:
                await member.add_roles(role, reason="self-assigned via #roles")
            else:
                await member.remove_roles(role, reason="un-assigned via #roles")
        except discord.HTTPException as exc:
            log.warning("role toggle failed for %s: %s", payload.user_id, exc.status)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RolePicker(bot))
