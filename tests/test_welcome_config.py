import asyncio

from bot.core.db import Database
from bot.core.models import GuildConfig

GUILD = 111111111111111111


def run(coro):
    return asyncio.run(coro)


def test_welcome_goodbye_channels_roundtrip(tmp_path):
    db = Database(tmp_path / "warden.db")

    async def scenario():
        await db.connect()
        await db.run_migrations()
        missing = await db.get_config(GUILD)
        config = GuildConfig(
            guild_id=GUILD,
            welcome_channel=987654321098765432,
            goodbye_channel=123456789012345678,
        )
        await db.set_config(config)
        loaded = await db.get_config(GUILD)
        await db.close()
        return missing, loaded

    missing, loaded = run(scenario())
    assert missing is None
    assert loaded is not None
    assert loaded.welcome_channel == 987654321098765432
    assert loaded.goodbye_channel == 123456789012345678


def test_welcome_channels_default_to_none(tmp_path):
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
    assert loaded.welcome_channel is None
    assert loaded.goodbye_channel is None
