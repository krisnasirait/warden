import asyncio

import pytest

from bot.core.db import Database
from bot.core.models import GuildConfig

GUILD = 111111111111111111
USER = 222222222222222222
MOD = 333333333333333333


def run(coro):
    return asyncio.run(coro)


def test_migrations_apply_on_fresh_db(tmp_path):
    db = Database(tmp_path / "warden.db")

    async def scenario():
        await db.connect()
        ran = await db.run_migrations()
        tables = {
            row["name"]
            for row in await db.conn.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        await db.close()
        return ran, tables

    ran, tables = run(scenario())
    assert ran == ["001_init.sql", "002_appeals.sql"]
    assert {"guild_config", "infractions", "appeals", "_migrations"} <= tables


def test_migrations_are_idempotent(tmp_path):
    db = Database(tmp_path / "warden.db")

    async def scenario():
        await db.connect()
        first = await db.run_migrations()
        second = await db.run_migrations()
        await db.close()
        return first, second

    first, second = run(scenario())
    assert first == ["001_init.sql", "002_appeals.sql"]
    assert second == []


def test_infraction_flow_and_counts(tmp_path):
    db = Database(tmp_path / "warden.db")

    async def scenario():
        await db.connect()
        await db.run_migrations()
        case1 = await db.add_infraction(GUILD, USER, MOD, "spam")
        case2 = await db.add_infraction(GUILD, USER, MOD, "links", source="automod")
        count = await db.active_infraction_count(GUILD, USER)
        cleared = await db.deactivate_infractions(GUILD, USER)
        after = await db.active_infraction_count(GUILD, USER)
        history = await db.history(GUILD, USER)
        await db.close()
        return case1, case2, count, cleared, after, history

    case1, case2, count, cleared, after, history = run(scenario())
    assert case1 == 1
    assert case2 == 2
    assert count == 2
    assert cleared == 2
    assert after == 0
    assert [h.id for h in history] == [2, 1]
    assert history[0].source == "automod"


def test_guild_config_roundtrip(tmp_path):
    db = Database(tmp_path / "warden.db")

    async def scenario():
        await db.connect()
        await db.run_migrations()
        missing = await db.get_config(GUILD)
        config = GuildConfig(
            guild_id=GUILD,
            mod_role=MOD,
            log_channel=999,
            escalation={2: "timeout", 4: "ban"},
            filters={"links": True},
        )
        await db.set_config(config)
        loaded = await db.get_config(GUILD)
        await db.close()
        return missing, loaded

    missing, loaded = run(scenario())
    assert missing is None
    assert loaded is not None
    assert loaded.mod_role == MOD
    assert loaded.escalation == {2: "timeout", 4: "ban"}
    assert loaded.filters == {"links": True}


def test_missing_db_raises_not_connected(tmp_path):
    db = Database(tmp_path / "x.db")
    with pytest.raises(RuntimeError, match="not connected"):
        run(db.active_infraction_count(GUILD, USER))
