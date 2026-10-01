import asyncio

import pytest

from bot.core.db import Database
from bot.core.models import GuildConfig
from bot.services.enforcement import record

GUILD = 111111111111111111
USER = 222222222222222222
MOD = 333333333333333333


def run(coro):
    return asyncio.run(coro)


def test_record_below_threshold_takes_no_action(tmp_path):
    db = Database(tmp_path / "warden.db")
    config = GuildConfig(guild_id=GUILD, escalation={3: "timeout"})

    async def scenario():
        await db.connect()
        await db.run_migrations()
        result = await record(
            db, config, guild_id=GUILD, user_id=USER, mod_id=MOD, reason="test"
        )
        active = await db.active_infraction_count(GUILD, USER)
        await db.close()
        return result, active

    result, active = run(scenario())
    assert result.infraction.id == 1
    assert result.action == "none"
    assert result.note is None
    assert result.active_count == 1
    assert active == 1


def test_record_automod_source(tmp_path):
    db = Database(tmp_path / "warden.db")
    config = GuildConfig(guild_id=GUILD, escalation={99: "ban"})

    async def scenario():
        await db.connect()
        await db.run_migrations()
        result = await record(
            db,
            config,
            guild_id=GUILD,
            user_id=USER,
            mod_id=0,
            reason="automod: spam",
            source="automod",
        )
        await db.close()
        return result

    result = run(scenario())
    assert result.infraction.source == "automod"
    assert result.infraction.mod_id == 0


def test_record_requires_member_when_action_triggers(tmp_path):
    db = Database(tmp_path / "warden.db")
    config = GuildConfig(guild_id=GUILD, escalation={1: "ban"})

    async def scenario():
        await db.connect()
        await db.run_migrations()
        with pytest.raises(ValueError, match="member is required"):
            await record(
                db, config, guild_id=GUILD, user_id=USER, mod_id=MOD, reason="x"
            )
        await db.close()

    run(scenario())
