import asyncio

from bot.core.db import Database
from bot.core.models import GuildConfig

GUILD = 111111111111111111


def run(coro):
    return asyncio.run(coro)


def test_verify_config_roundtrip(tmp_path):
    db = Database(tmp_path / "warden.db")

    async def scenario():
        await db.connect()
        await db.run_migrations()
        missing = await db.get_config(GUILD)
        config = GuildConfig(
            guild_id=GUILD,
            verified_role=111,
            verify_channel=222,
            verify_message=333,
        )
        await db.set_config(config)
        loaded = await db.get_config(GUILD)
        await db.close()
        return missing, loaded

    missing, loaded = run(scenario())
    assert missing is None
    assert loaded is not None
    assert loaded.verified_role == 111
    assert loaded.verify_channel == 222
    assert loaded.verify_message == 333


def test_verify_defaults_none(tmp_path):
    db = Database(tmp_path / "warden.db")

    async def scenario():
        await db.connect()
        await db.run_migrations()
        config = GuildConfig(guild_id=GUILD)
        await db.set_config(config)
        loaded = await db.get_config(GUILD)
        await db.close()
        return loaded

    loaded = run(scenario())
    assert loaded is not None
    assert loaded.verified_role is None
    assert loaded.verify_message is None
