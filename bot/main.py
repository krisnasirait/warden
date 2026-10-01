from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands, tasks

from bot.core.config import Settings
from bot.core.db import Database

log = logging.getLogger("warden")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class Warden(commands.Bot):
    def __init__(self, settings: Settings, db: Database) -> None:
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.db = db
        self._commands_synced = False

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
        if self.settings.heartbeat_channel:
            self.heartbeat_loop.start()

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
