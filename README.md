# warden

Discord moderation bot for a single guild: automod, infractions with
auto-escalation, case logging, raid lockdown, and a Discord-only appeal flow.

## Stack

- Python 3.13 + discord.py 2.4 (slash commands only)
- SQLite (aiosqlite) on the EC2 EBS volume
- Token via SSM Parameter Store (`/warden/discord-token`), never on disk
- Deployed as one Docker container on a free-tier `t3.micro`

## Discord application setup

1. Create the app at <https://discord.com/developers/applications> → Bot.
2. Enable **privileged intents**: `MESSAGE CONTENT INTENT` and
   `SERVER MEMBERS INTENT`. Automod silently reads nothing without them.
3. Invite with scopes `bot applications.commands` and permissions:
   Send Messages, Embed Links, Manage Messages, Moderate Members, Kick, Ban,
   Create Public Threads, Create Private Threads, Read Message History.
4. Store the bot token in SSM (never in git, never in `.env`):

   ```bash
   aws ssm put-parameter --name /warden/discord-token \
       --type SecureString --value "<token>"
   ```

   Note: the default `alias/aws/ssm` key expires in 7 days — re-put the
   parameter on rotation, or encrypt with a customer-managed KMS key.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest
python -m bot.main          # needs DISCORD_TOKEN in env locally
```

## Configuration

Environment variables:

| Var | Default | Purpose |
|---|---|---|
| `DISCORD_TOKEN` | — | Bot token (locally only; on EC2 injected from SSM) |
| `DB_PATH` | `data/warden.db` | SQLite file location |
| `HEARTBEAT_CHANNEL` | unset | Channel whose message the bot edits every 5 min |

In-guild config lives in the database, editable at runtime via `/config`
(mod role, log channel, escalation thresholds, filter lists).

## Migrations

Numbered SQL files in `migrations/`, applied in order, recorded in the
`_migrations` table. Never edit an applied migration — add a new one.

## Operations

- Data survives instance termination only if the EBS volume is kept;
  nightly `sqlite3 .backup` → S3 is the real safety net (D5).
- Cost: $0/mo inside the AWS free tier (t3.micro 750h, 30GB EBS, 5GB S3).
  After 12 months expect ~$8–10/mo.
