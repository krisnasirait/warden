from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from bot.core.models import Appeal, GuildConfig, Infraction

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


class Database:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("database not connected")
        return self._conn

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def run_migrations(self, directory: Path | str = MIGRATIONS_DIR) -> list[str]:
        await self.conn.execute(
            "CREATE TABLE IF NOT EXISTS _migrations ("
            "name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {
            row["name"]
            for row in await self.conn.execute_fetchall("SELECT name FROM _migrations")
        }
        ran: list[str] = []
        for sql_file in sorted(Path(directory).glob("*.sql")):
            if sql_file.name in applied:
                continue
            await self.conn.executescript(sql_file.read_text())
            await self.conn.execute(
                "INSERT INTO _migrations (name, applied_at) VALUES (?, ?)",
                (sql_file.name, datetime.now(UTC).isoformat()),
            )
            await self.conn.commit()
            ran.append(sql_file.name)
        return ran

    async def get_config(self, guild_id: int) -> GuildConfig | None:
        row = await self.conn.execute_fetchall(
            "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
        )
        return GuildConfig.from_row(row[0]) if row else None

    async def set_config(self, config: GuildConfig) -> None:
        await self.conn.execute(
            "INSERT INTO guild_config (guild_id, mod_role, log_channel,"
            " escalation_json, filters_json, lockdown, appeal_guild,"
            " welcome_channel, goodbye_channel, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET"
            " mod_role = excluded.mod_role, log_channel = excluded.log_channel,"
            " escalation_json = excluded.escalation_json,"
            " filters_json = excluded.filters_json, lockdown = excluded.lockdown,"
            " appeal_guild = excluded.appeal_guild,"
            " welcome_channel = excluded.welcome_channel,"
            " goodbye_channel = excluded.goodbye_channel,"
            " updated_at = excluded.updated_at",
            (
                config.guild_id,
                config.mod_role,
                config.log_channel,
                config.escalation_json(),
                config.filters_json(),
                int(config.lockdown),
                config.appeal_guild,
                config.welcome_channel,
                config.goodbye_channel,
                datetime.now(UTC).isoformat(),
            ),
        )
        await self.conn.commit()

    async def find_by_appeal_guild(self, appeal_guild_id: int) -> GuildConfig | None:
        rows = await self.conn.execute_fetchall(
            "SELECT * FROM guild_config WHERE appeal_guild = ?", (appeal_guild_id,)
        )
        return GuildConfig.from_row(rows[0]) if rows else None

    async def add_infraction(
        self,
        guild_id: int,
        user_id: int,
        mod_id: int,
        reason: str,
        source: str = "manual",
    ) -> int:
        cursor = await self.conn.execute(
            "INSERT INTO infractions (guild_id, user_id, mod_id, reason, source)"
            " VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, mod_id, reason, source),
        )
        await self.conn.commit()
        return int(cursor.lastrowid)

    async def active_infraction_count(self, guild_id: int, user_id: int) -> int:
        row = await self.conn.execute_fetchall(
            "SELECT COUNT(*) AS n FROM infractions"
            " WHERE guild_id = ? AND user_id = ? AND active = 1",
            (guild_id, user_id),
        )
        return int(row[0]["n"])

    async def deactivate_infractions(self, guild_id: int, user_id: int) -> int:
        cursor = await self.conn.execute(
            "UPDATE infractions SET active = 0"
            " WHERE guild_id = ? AND user_id = ? AND active = 1",
            (guild_id, user_id),
        )
        await self.conn.commit()
        return cursor.rowcount

    async def get_infraction(self, guild_id: int, case_id: int) -> Infraction | None:
        rows = await self.conn.execute_fetchall(
            "SELECT * FROM infractions WHERE guild_id = ? AND id = ?",
            (guild_id, case_id),
        )
        if not rows:
            return None
        row = rows[0]
        return Infraction(
            id=row["id"],
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            mod_id=row["mod_id"],
            reason=row["reason"],
            source=row["source"],
            active=bool(row["active"]),
            created_at=row["created_at"],
        )

    async def deactivate_case(self, guild_id: int, case_id: int) -> bool:
        cursor = await self.conn.execute(
            "UPDATE infractions SET active = 0"
            " WHERE guild_id = ? AND id = ? AND active = 1",
            (guild_id, case_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def history(self, guild_id: int, user_id: int) -> list[Infraction]:
        rows = await self.conn.execute_fetchall(
            "SELECT * FROM infractions WHERE guild_id = ? AND user_id = ?"
            " ORDER BY id DESC",
            (guild_id, user_id),
        )
        return [
            Infraction(
                id=row["id"],
                guild_id=row["guild_id"],
                user_id=row["user_id"],
                mod_id=row["mod_id"],
                reason=row["reason"],
                source=row["source"],
                active=bool(row["active"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    @staticmethod
    def _appeal_from_row(row) -> Appeal:
        return Appeal(
            id=row["id"],
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            case_id=row["case_id"],
            status=row["status"],
            statement=row["statement"],
            resolved_by=row["resolved_by"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
            thread_id=row["thread_id"],
        )

    async def create_appeal(self, guild_id: int, user_id: int, statement: str) -> int:
        try:
            cursor = await self.conn.execute(
                "INSERT INTO appeals (guild_id, user_id, statement) VALUES (?, ?, ?)",
                (guild_id, user_id, statement),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("user already has a pending appeal") from exc
        await self.conn.commit()
        return int(cursor.lastrowid)

    async def set_appeal_thread(self, guild_id: int, appeal_id: int, thread_id: int) -> None:
        await self.conn.execute(
            "UPDATE appeals SET thread_id = ? WHERE guild_id = ? AND id = ?",
            (thread_id, guild_id, appeal_id),
        )
        await self.conn.commit()

    async def pending_appeal(self, guild_id: int, user_id: int) -> int | None:
        rows = await self.conn.execute_fetchall(
            "SELECT id FROM appeals"
            " WHERE guild_id = ? AND user_id = ? AND status = 'pending'",
            (guild_id, user_id),
        )
        return int(rows[0]["id"]) if rows else None

    async def get_appeal(self, guild_id: int, appeal_id: int) -> Appeal | None:
        rows = await self.conn.execute_fetchall(
            "SELECT * FROM appeals WHERE guild_id = ? AND id = ?",
            (guild_id, appeal_id),
        )
        return self._appeal_from_row(rows[0]) if rows else None

    async def resolve_appeal(
        self, guild_id: int, appeal_id: int, status: str, resolver_id: int
    ) -> bool:
        cursor = await self.conn.execute(
            "UPDATE appeals SET status = ?, resolved_by = ?, resolved_at = ?"
            " WHERE guild_id = ? AND id = ? AND status = 'pending'",
            (
                status,
                resolver_id,
                datetime.now(UTC).isoformat(),
                guild_id,
                appeal_id,
            ),
        )
        await self.conn.commit()
        return cursor.rowcount > 0
