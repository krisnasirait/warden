import asyncio

from bot.core.db import Database

GUILD = 111111111111111111
USER = 222222222222222222
MOD = 333333333333333333


def run(coro):
    return asyncio.run(coro)


def test_get_and_deactivate_single_case(tmp_path):
    db = Database(tmp_path / "warden.db")

    async def scenario():
        await db.connect()
        await db.run_migrations()
        case1 = await db.add_infraction(GUILD, USER, MOD, "first")
        case2 = await db.add_infraction(GUILD, USER, MOD, "second")
        fetched = await db.get_infraction(GUILD, case1)
        missing = await db.get_infraction(GUILD, 999)
        deactivated = await db.deactivate_case(GUILD, case1)
        after_one = await db.get_infraction(GUILD, case1)
        still_active = await db.get_infraction(GUILD, case2)
        active_count = await db.active_infraction_count(GUILD, USER)
        again = await db.deactivate_case(GUILD, case1)
        await db.close()
        return fetched, missing, deactivated, after_one, still_active, active_count, again

    fetched, missing, deactivated, after_one, still_active, active_count, again = run(scenario())
    assert fetched is not None
    assert fetched.reason == "first"
    assert missing is None
    assert deactivated is True
    assert after_one is not None and not after_one.active
    assert still_active is not None and still_active.active
    assert active_count == 1
    assert again is False


def test_unwarn_by_mod_scoped_to_guild(tmp_path):
    db = Database(tmp_path / "warden.db")
    OTHER_GUILD = 999

    async def scenario():
        await db.connect()
        await db.run_migrations()
        case = await db.add_infraction(GUILD, USER, MOD, "x")
        other_guild_view = await db.get_infraction(OTHER_GUILD, case)
        deactivated = await db.deactivate_case(OTHER_GUILD, case)
        await db.close()
        return other_guild_view, deactivated

    other_guild_view, deactivated = run(scenario())
    assert other_guild_view is None
    assert deactivated is False
