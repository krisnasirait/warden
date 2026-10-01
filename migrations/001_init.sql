CREATE TABLE IF NOT EXISTS guild_config (
    guild_id       INTEGER PRIMARY KEY,
    mod_role       INTEGER,
    log_channel    INTEGER,
    escalation_json TEXT NOT NULL DEFAULT '{"3": "timeout", "5": "kick", "7": "ban"}',
    filters_json   TEXT NOT NULL DEFAULT '{}',
    lockdown       INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS infractions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    mod_id     INTEGER NOT NULL,
    reason     TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'manual',
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_infractions_user
    ON infractions (guild_id, user_id, active);

CREATE TABLE IF NOT EXISTS appeals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id     INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    case_id      INTEGER REFERENCES infractions(id),
    status       TEXT NOT NULL DEFAULT 'pending',
    statement    TEXT NOT NULL,
    resolved_by  INTEGER,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at  TEXT
);
