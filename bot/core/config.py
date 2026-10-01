from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    discord_token: str
    db_path: Path
    heartbeat_channel: int | None = None

    @classmethod
    def from_env(cls) -> Settings:
        token = os.environ.get("DISCORD_TOKEN", "")
        if not token:
            raise SystemExit("DISCORD_TOKEN is not set (on EC2 it is injected from SSM)")
        heartbeat = os.environ.get("HEARTBEAT_CHANNEL")
        return cls(
            discord_token=token,
            db_path=Path(os.environ.get("DB_PATH", "data/warden.db")),
            heartbeat_channel=int(heartbeat) if heartbeat else None,
        )
