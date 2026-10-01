ALTER TABLE guild_config ADD COLUMN appeal_guild INTEGER;

ALTER TABLE appeals ADD COLUMN thread_id INTEGER;

CREATE UNIQUE INDEX IF NOT EXISTS idx_appeals_pending
    ON appeals (guild_id, user_id) WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_appeals_status ON appeals (status, guild_id);
