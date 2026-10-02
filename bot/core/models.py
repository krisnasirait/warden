from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class GuildConfig:
    guild_id: int
    mod_role: int | None = None
    log_channel: int | None = None
    escalation: dict[int, str] = field(
        default_factory=lambda: {3: "timeout", 5: "kick", 7: "ban"}
    )
    filters: dict = field(default_factory=dict)
    lockdown: bool = False
    appeal_guild: int | None = None
    welcome_channel: int | None = None
    goodbye_channel: int | None = None
    verified_role: int | None = None
    verify_channel: int | None = None
    verify_message: int | None = None

    @classmethod
    def from_row(cls, row) -> GuildConfig:
        return cls(
            guild_id=row["guild_id"],
            mod_role=row["mod_role"],
            log_channel=row["log_channel"],
            escalation={int(k): v for k, v in json.loads(row["escalation_json"]).items()},
            filters=json.loads(row["filters_json"]),
            lockdown=bool(row["lockdown"]),
            appeal_guild=row["appeal_guild"],
            welcome_channel=row["welcome_channel"],
            goodbye_channel=row["goodbye_channel"],
            verified_role=row["verified_role"],
            verify_channel=row["verify_channel"],
            verify_message=row["verify_message"],
        )

    def escalation_json(self) -> str:
        return json.dumps({str(k): v for k, v in sorted(self.escalation.items())})

    def filters_json(self) -> str:
        return json.dumps(self.filters)


@dataclass
class Infraction:
    id: int
    guild_id: int
    user_id: int
    mod_id: int
    reason: str
    source: str = "manual"
    active: bool = True
    created_at: str = field(default_factory=_now)


@dataclass
class Appeal:
    id: int
    guild_id: int
    user_id: int
    case_id: int | None
    status: str
    statement: str
    resolved_by: int | None
    created_at: str
    resolved_at: str | None
    thread_id: int | None
