import asyncio

import pytest

from bot.core.db import Database
from bot.core.models import GuildConfig

GUILD = 111111111111111111
APPEAL_GUILD = 444444444444444444
USER = 222222222222222222
MOD = 333333333333333333


def run(coro):
    return asyncio.run(coro)


def test_appeal_lifecycle(tmp_path):
    db = Database(tmp_path / "warden.db")

    async def scenario():
        await db.connect()
        await db.run_migrations()
        aid = await db.create_appeal(GUILD, USER, "please reconsider")
        pending = await db.pending_appeal(GUILD, USER)
        fetched = await db.get_appeal(GUILD, aid)
        await db.set_appeal_thread(GUILD, aid, 555)
        resolved = await db.resolve_appeal(GUILD, aid, "approved", MOD)
        fetched_again = await db.get_appeal(GUILD, aid)
        pending_after = await db.pending_appeal(GUILD, USER)
        resolved_twice = await db.resolve_appeal(GUILD, aid, "denied", MOD)
        await db.close()
        return (
            aid, pending, fetched, resolved, fetched_again,
            pending_after, resolved_twice,
        )

    aid, pending, fetched, resolved, fetched_again, pending_after, resolved_twice = (
        run(scenario())
    )
    assert aid == 1
    assert pending == 1
    assert fetched is not None and fetched.statement == "please reconsider"
    assert resolved is True
    assert fetched_again is not None
    assert fetched_again.status == "approved"
    assert fetched_again.resolved_by == MOD
    assert fetched_again.thread_id == 555
    assert pending_after is None
    assert resolved_twice is False


def test_second_pending_appeal_rejected(tmp_path):
    db = Database(tmp_path / "warden.db")

    async def scenario():
        await db.connect()
        await db.run_migrations()
        await db.create_appeal(GUILD, USER, "first")
        with pytest.raises(ValueError, match="pending"):
            await db.create_appeal(GUILD, USER, "second")
        await db.resolve_appeal(GUILD, 1, "denied", MOD)
        third_id = await db.create_appeal(GUILD, USER, "third try")
        await db.close()
        return third_id

    third_id = run(scenario())
    # rejected insert consumes no ID, so the successful third create is #2
    assert third_id == 2


def test_find_config_by_appeal_guild(tmp_path):
    db = Database(tmp_path / "warden.db")

    async def scenario():
        await db.connect()
        await db.run_migrations()
        before = await db.find_by_appeal_guild(APPEAL_GUILD)
        config = GuildConfig(
            guild_id=GUILD,
            mod_role=MOD,
            log_channel=999,
            appeal_guild=APPEAL_GUILD,
        )
        await db.set_config(config)
        after = await db.find_by_appeal_guild(APPEAL_GUILD)
        other = await db.find_by_appeal_guild(123)
        await db.close()
        return before, after, other

    before, after, other = run(scenario())
    assert before is None
    assert after is not None
    assert after.guild_id == GUILD
    assert after.appeal_guild == APPEAL_GUILD
    assert other is None


def test_appeal_guild_roundtrip_with_filters(tmp_path):
    db = Database(tmp_path / "warden.db")

    async def scenario():
        await db.connect()
        await db.run_migrations()
        config = GuildConfig(
            guild_id=GUILD,
            filters={"words": ["spam"], "prev_verification": 2},
            appeal_guild=APPEAL_GUILD,
        )
        await db.set_config(config)
        loaded = await db.get_config(GUILD)
        await db.close()
        return loaded

    loaded = run(scenario())
    assert loaded is not None
    assert loaded.appeal_guild == APPEAL_GUILD
    assert loaded.filters["words"] == ["spam"]
    assert loaded.filters["prev_verification"] == 2
