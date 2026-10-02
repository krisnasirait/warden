from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import discord
from discord.ext import commands, tasks

from bot.core.config import Settings
from bot.core.db import Database

log = logging.getLogger("warden")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

HEALTH_INTERVAL_HOURS = 12


def _humanize_uptime(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


class Warden(commands.Bot):
    def __init__(self, settings: Settings, db: Database) -> None:
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.db = db
        self._commands_synced = False
        self._started_at = discord.utils.utcnow()

    async def setup_hook(self) -> None:
        await self.db.connect()
        ran = await self.db.run_migrations()
        if ran:
            log.info("migrations applied: %s", ", ".join(ran))
        await self.load_extension("bot.cogs.infractions")
        await self.load_extension("bot.cogs.automod")
        await self.load_extension("bot.cogs.raid")
        await self.load_extension("bot.cogs.appeals")
        await self.load_extension("bot.cogs.config")
        await self.load_extension("bot.cogs.welcome")
        await self.load_extension("bot.cogs.verify")
        if self.settings.heartbeat_channel:
            self.heartbeat_loop.start()
        self.health_loop.start()

    async def on_ready(self) -> None:
        log.info("connected as %s (%s)", self.user, self.user and self.user.id)
        if not self._commands_synced:
            # guild-synced commands appear instantly (global sync takes up to 1h)
            for guild in self.guilds:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            self._commands_synced = True
            log.info("slash commands synced to %d guild(s)", len(self.guilds))

    @tasks.loop(minutes=5)
    async def heartbeat_loop(self) -> None:
        try:
            channel = self.get_channel(self.settings.heartbeat_channel)
            if not isinstance(channel, discord.TextChannel):
                log.warning(
                    "heartbeat channel %s not in cache", self.settings.heartbeat_channel
                )
                return
            embed = discord.Embed(title="warden alive", color=discord.Color.green())
            embed.timestamp = discord.utils.utcnow()
            # edit-or-post: keep one status message, never spam the channel
            async for msg in channel.history(limit=50):
                if (
                    msg.author == self.user
                    and msg.embeds
                    and msg.embeds[0].title == "warden alive"
                ):
                    await msg.edit(embed=embed)
                    return
            await channel.send(embed=embed)
        except Exception:
            log.exception("heartbeat failed")

    @heartbeat_loop.before_loop
    async def before_heartbeat(self) -> None:
        # don't attempt before guilds/channels are cached
        await self.wait_until_ready()

    @tasks.loop(hours=HEALTH_INTERVAL_HOURS)
    async def health_loop(self) -> None:
        try:
            for guild in self.guilds:
                channel = await self._mod_log(guild)
                if channel is None:
                    log.warning("health check: no mod-log channel in %s", guild.id)
                    continue
                await channel.send(embed=await self._health_embed(guild))
        except Exception:
            log.exception("health check failed")

    @health_loop.before_loop
    async def before_health(self) -> None:
        await self.wait_until_ready()

    async def _mod_log(self, guild: discord.Guild) -> discord.TextChannel | None:
        config = await self.db.get_config(guild.id)
        if config and config.log_channel:
            channel = guild.get_channel(config.log_channel)
            if isinstance(channel, discord.TextChannel):
                return channel
        return next(
            (c for c in guild.text_channels if c.name.lower() == "mod-log"), None
        )

    async def _infraction_count(self) -> int:
        try:
            rows = await self.db.conn.execute_fetchall(
                "SELECT COUNT(*) AS n FROM infractions"
            )
            return int(rows[0]["n"])
        except Exception:
            return 0

    async def _health_embed(self, guild: discord.Guild) -> discord.Embed:
        now = discord.utils.utcnow()
        embed = discord.Embed(
            title="Warden health check",
            color=discord.Color.green(),
            timestamp=now,
        )
        latency = self.latency
        latency_txt = (
            f"{int(latency * 1000)} ms" if latency == latency and latency < 60 else "n/a"
        )
        embed.add_field(name="Status", value="🟢 online", inline=True)
        embed.add_field(
            name="Uptime",
            value=_humanize_uptime(now - self._started_at),
            inline=True,
        )
        embed.add_field(name="Gateway", value=latency_txt, inline=True)
        embed.add_field(name="Servers", value=str(len(self.guilds)), inline=True)
        embed.add_field(
            name="Members",
            value=str(sum(g.member_count or 0 for g in self.guilds)),
            inline=True,
        )
        embed.add_field(
            name="Infractions logged",
            value=str(await self._infraction_count()),
            inline=True,
        )
        embed.set_footer(text=f"health check every {HEALTH_INTERVAL_HOURS} hours")
        return embed

    async def close(self) -> None:
        await self.db.close()
        await super().close()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    bot = Warden(settings, Database(settings.db_path))
    async with bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
