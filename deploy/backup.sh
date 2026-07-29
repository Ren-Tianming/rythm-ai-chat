#!/bin/sh
set -eu

project_dir="${RYTHM_PROJECT_DIR:-/opt/rythm-chatbot}"
env_file="${RYTHM_ENV_FILE:-${project_dir}/.env}"
backup_dir="${RYTHM_BACKUP_DIR:-/var/backups/rythm-chatbot}"
retention_days="${RYTHM_BACKUP_RETENTION_DAYS:-7}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${backup_dir}/rythm-${timestamp}.sql.gz"
temporary="${target}.partial"

cd "$project_dir"
test -f "$env_file"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"

docker compose --env-file "$env_file" exec -T db sh -c \
  'pg_dump --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  | gzip -9 > "$temporary"

test -s "$temporary"
gzip -t "$temporary"
chmod 600 "$temporary"
mv "$temporary" "$target"
find "$backup_dir" -type f -name 'rythm-*.sql.gz' -mtime "+$retention_days" -delete
printf '%s\n' "$target"
