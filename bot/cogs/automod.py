from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

import discord
from discord.ext import commands

from bot.cogs.base import WardenCog
from bot.services import filters as F
from bot.services.enforcement import case_embed, record, send_case_log

log = logging.getLogger("warden.automod")

MAX_TRACK_SECONDS = 600.0
# slug, human name for reasons
LINK_RULES = {"invite": "invite link", "raw_ip": "raw IP address", "link": "link"}


class Automod(WardenCog):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)
        self._recent: dict[tuple[int, int], deque[float]] = defaultdict(deque)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return

        config = await self.config(message.guild.id)

        if config.lockdown and not self.is_staff(message.author, config):
            await self._delete(message)
            return
        if self.is_staff(message.author, config):
            return

        key = (message.guild.id, message.author.id)
        now = time.time()
        bucket = self._recent[key]
        bucket.append(now)
        while bucket and now - bucket[0] > MAX_TRACK_SECONDS:
            bucket.popleft()

        filters = config.filters or {}
        rate = {**F.DEFAULT_RATE, **filters.get("rate", {})}
        links = {**F.DEFAULT_LINKS, **filters.get("links", {})}
        words = filters.get("words", [])

        rule = self._match_rule(message.content or "", list(bucket), rate, links, words)
        if rule is None:
            return

        bucket.clear()
        await self._delete(message)
        result = await record(
            self.bot.db,
            config,
            guild_id=message.guild.id,
            user_id=message.author.id,
            mod_id=0,
            reason=f"automod: {rule}",
            source="automod",
            member=message.author,
        )
        embed = case_embed(result.infraction, result.action, result.active_count, result.note)
        await send_case_log(config, message.guild, embed)
        await self._notify(message, result.infraction.id, rule)

    def _match_rule(
        self,
        content: str,
        timestamps: list[float],
        rate: dict,
        links: dict,
        words: list[str],
    ) -> str | None:
        if F.within_window(timestamps, int(rate["count"]), float(rate["window"])):
            return f"spam ({rate['count']} msgs in {rate['window']}s)"
        hit = F.link_hit(
            content,
            block_invites=bool(links.get("block_invites", True)),
            block_raw_ips=bool(links.get("block_raw_ips", True)),
            block_all_links=bool(links.get("block_all_links", False)),
            allowlist=links.get("allowlist") or [],
        )
        if hit:
            return LINK_RULES.get(hit, hit)
        word = F.word_hit(content, words)
        if word:
            shown = word if len(word) <= 60 else f"{word[:57]}..."
            return f"word filter /{shown}/"
        return None

    @staticmethod
    async def _delete(message: discord.Message) -> None:
        try:
            await message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            log.warning("missing Manage Messages in %s", message.guild and message.guild.id)

    @staticmethod
    async def _notify(message: discord.Message, case_id: int, rule: str) -> None:
        try:
            await message.author.send(
                f"Your message in **{message.guild.name}** was removed "
                f"(case #{case_id}): {rule}"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Automod(bot))
