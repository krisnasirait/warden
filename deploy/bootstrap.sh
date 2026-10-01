#!/usr/bin/env bash
# EC2 bootstrap for warden — Ubuntu 24.04, free-tier t3.micro. Idempotent-ish.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update -y
apt-get install -y docker.io docker-compose-v2 ufw fail2ban sqlite3 unattended-upgrades

systemctl enable --now docker
systemctl enable --now fail2ban
systemctl enable unattended-upgrades

# Real SSH boundary is the security group (locked to your IP — edit it in the
# console if your IP changes). ufw allows SSH from anywhere so a rotated IP
# never locks you out; auth is still key-only.
ufw default deny incoming
ufw allow OpenSSH
ufw --force enable

if [ ! -d /opt/warden/.git ]; then
  git clone https://github.com/krisnasirait/warden.git /opt/warden
fi
cd /opt/warden

# AWS CLI (for token fetch + backup cron)
if ! command -v aws >/dev/null; then
  snap install aws-cli --classic
fi

# Token: SSM (instance role) -> local env file, 0600, gitignored. Never printed.
TOKEN="$(aws ssm get-parameter --name /warden/discord-token --with-decryption \
  --query Parameter.Value --output text)"
umask 077
printf 'DISCORD_TOKEN=%s\n' "$TOKEN" > deploy/.env
chmod 600 deploy/.env
unset TOKEN

cd deploy
docker compose up -d --build

# Nightly backup: sqlite .backup -> gzip -> S3, 7-day retention.
cat > /usr/local/sbin/warden-backup <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin
DB=/opt/warden/deploy/data/warden.db
BUCKET=s3://warden-backups-261732724084
[ -f "$DB" ] || exit 0
STAMP=$(date +%F-%H%M)
sqlite3 "$DB" ".backup /tmp/warden-$STAMP.db"
gzip -c "/tmp/warden-$STAMP.db" | aws s3 cp - "$BUCKET/warden-$STAMP.db.gz"
rm -f "/tmp/warden-$STAMP.db"
CUT="$(date -d '7 days ago' +%Y-%m-%d)"
aws s3 ls "$BUCKET/" | awk -v cut="warden-$CUT" '$4 < cut {print $4}' \
  | while read -r f; do [ -n "$f" ] && aws s3 rm "$BUCKET/$f"; done
EOS
chmod +x /usr/local/sbin/warden-backup
echo "17 3 * * * root /usr/local/sbin/warden-backup" > /etc/cron.d/warden-backup

echo "BOOTSTRAP DONE"
