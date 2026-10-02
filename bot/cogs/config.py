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
        embed.add_field(
            name="Verification",
            value=(
                f"armed · role {config.verified_role}"
                if config.verify_message
                else "*not set up*"
            ),
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
        name="setup-verification",
        description="Post the ✅ message in #rules that gates the server",
    )
    async def setup_verification(self, interaction: discord.Interaction) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        config = await self.config(interaction.guild_id)
        guild = interaction.guild

        rules = guild.get_channel(config.verify_channel) if config.verify_channel else None
        if not isinstance(rules, discord.TextChannel):
            rules = next(
                (c for c in guild.text_channels if c.name.lower() == "rules"), None
            )
        if rules is None:
            await interaction.followup.send("No `#rules` channel found.", ephemeral=True)
            return

        # remove any previous verification message so reruns swap instead of stack
        if config.verify_message:
            old_channel = (
                guild.get_channel(config.verify_channel)
                if config.verify_channel
                else rules
            )
            if isinstance(old_channel, discord.TextChannel):
                try:
                    old = await old_channel.fetch_message(config.verify_message)
                    await old.delete()
                except discord.HTTPException:
                    pass

        role = guild.get_role(config.verified_role) if config.verified_role else None
        if role is None:
            role = discord.utils.get(guild.roles, name="Verified")
        if role is None:
            await interaction.followup.send(
                "No `Verified` role found — create it first.", ephemeral=True
            )
            return

        eros = discord.utils.get(guild.roles, name="EROS")
        roles_channel = next(
            (c for c in guild.text_channels if c.name.lower() == "roles"), None
        )
        eros_ref = f"<@&{eros.id}>" if eros else "@EROS"
        roles_ref = f"<#{roles_channel.id}>" if roles_channel else "#roles"

        embed = discord.Embed(
            title="Rules (baca dulu ya)",
            description=(
                "Baca bentar, terus **klik ✅ di bawah** buat buka semua channel."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Ngobrol",
            value=(
                "1. No toxic, rasis, SARA, atau nge-bully orang.\n"
                "2. Sama-sama respect, beda pendapat mah biasa."
            ),
            inline=False,
        )
        embed.add_field(
            name="Konten",
            value=(
                "3. Jangan share porn / NSFW.\n"
                "4. Jangan share hal di luar komunitas yang bisa bikin salah paham."
            ),
            inline=False,
        )
        embed.add_field(
            name="Spam & Iklan",
            value=(
                "5. No spam, flood, atau mention massal.\n"
                "6. Jangan promosi / jualan yang cuma untungin diri sendiri."
            ),
            inline=False,
        )
        embed.add_field(
            name="Nama & Identitas",
            value=(
                "7. Nickname dipake yang bener, sesuai kolom. Nama toxic dilarang.\n"
                "8. Jangan ngaku moderator atau minta jadi mod."
            ),
            inline=False,
        )
        embed.add_field(
            name="Yang lain",
            value=(
                f"9. Butuh admin? Tag {eros_ref}.\n"
                f"10. Mau buka chat? Ambil role di {roles_ref}, klik emoji aja."
                "\n\n"
                "Pelanggaran: warning → timeout → kick → ban.\n"
                "Makasih udah baca 😍"
            ),
            inline=False,
        )
        try:
            message = await rules.send(embed=embed)
            await message.add_reaction("✅")
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"Could not post in {rules.mention} ({exc.status}).", ephemeral=True
            )
            return

        config.verify_channel = rules.id
        config.verify_message = message.id
        config.verified_role = role.id
        await self.bot.db.set_config(config)

        await interaction.followup.send(
            f"Rules + verification live in {rules.mention} — gated on {role.mention}.",
            ephemeral=True,
        )

    @cfg.command(
        name="setup-role-picker",
        description="Post the role picker in #roles (create + react)",
    )
    async def setup_role_picker(self, interaction: discord.Interaction) -> None:
        if await self.deny_if_not_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        config = await self.config(interaction.guild_id)
        guild = interaction.guild
        old = (config.filters or {}).get("role_picker") or {}

        channel = guild.get_channel(old.get("channel")) if old.get("channel") else None
        if not isinstance(channel, discord.TextChannel):
            channel = next(
                (c for c in guild.text_channels if c.name.lower() == "roles"), None
            )
        if channel is None:
            await interaction.followup.send("No `#roles` channel found.", ephemeral=True)
            return

        if old.get("message"):
            try:
                stale = await channel.fetch_message(old["message"])
                await stale.delete()
            except discord.HTTPException:
                pass

        specs = [
            ("Gaming", "\U0001f3ae"),
            ("Music", "\U0001f3b5"),
            ("Events", "\U0001f389"),
            ("Announcements", "\U0001f4e2"),
        ]
        warden_pos = max(r.position for r in guild.roles if r.name == "Warden")
        mapping: dict[str, int] = {}
        created = []
        for name, emoji in specs:
            role = discord.utils.get(guild.roles, name=name)
            if role is None:
                try:
                    role = await guild.create_role(
                        name=name,
                        permissions=discord.Permissions.none(),
                        mentionable=True,
                        reason="role picker",
                    )
                except discord.HTTPException as exc:
                    await interaction.followup.send(
                        f"Could not create `{name}` role ({exc.status}).",
                        ephemeral=True,
                    )
                    return
                created.append(name)
            if role.position >= warden_pos:
                await interaction.followup.send(
                    f"`{name}` sits at or above Warden — drag it below Warden, then retry.",
                    ephemeral=True,
                )
                return
            mapping[emoji] = role.id

        embed = discord.Embed(
            title="Pick your roles",
            description=(
                "Klik emoji di bawah buat ambil role, klik lagi buat lepas.\n"
                "Role ini buat dapet ping doang — bukan akses.\n\n"
                "\U0001f3ae Gaming\n\U0001f3b5 Music\n\U0001f389 Events\n"
                "\U0001f4e2 Announcements"
            ),
            color=discord.Color.blurple(),
        )
        try:
            message = await channel.send(embed=embed)
            for emoji in mapping:
                await message.add_reaction(emoji)
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"Could not post in {channel.mention} ({exc.status}).", ephemeral=True
            )
            return

        config.filters = dict(config.filters or {})
        config.filters["role_picker"] = {
            "channel": channel.id,
            "message": message.id,
            "roles": mapping,
        }
        await self.bot.db.set_config(config)

        made = f" (created {', '.join(created)})" if created else ""
        await interaction.followup.send(
            f"Role picker live in {channel.mention}{made} — {len(mapping)} roles.",
            ephemeral=True,
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
