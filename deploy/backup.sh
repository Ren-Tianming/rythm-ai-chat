#!/bin/sh
set -eu

project_dir="${RYTHM_PROJECT_DIR:-/opt/rythm-chatbot}"
env_file="${RYTHM_ENV_FILE:-${project_dir}/.env}"
backup_dir="${RYTHM_BACKUP_DIR:-/var/backups/rythm-chatbot}"
retention_days="${RYTHM_BACKUP_RETENTION_DAYS:-7}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${backup_dir}/rythm-${timestamp}"
temporary="${target}.partial"

cd "$project_dir"
test -f "$env_file"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
mkdir -m 700 "$temporary"
# Pause document/chat writes for a consistent DB + private-file snapshot.
docker compose --env-file "$env_file" stop web backend document-worker
restart() { docker compose --env-file "$env_file" up -d backend document-worker web; }
trap restart EXIT HUP INT TERM
# Separate dump from compression so a failed pg_dump cannot look successful.
docker compose --env-file "$env_file" exec -T db sh -c \
  'pg_dump --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$temporary/database.sql"
test -s "$temporary/database.sql"
gzip -9 "$temporary/database.sql"
docker compose --env-file "$env_file" run --rm --no-deps -T --entrypoint tar backend \
  -C /app/uploads -czf - . > "$temporary/uploads.tar.gz"
gzip -t "$temporary/database.sql.gz"
tar -tzf "$temporary/uploads.tar.gz" >/dev/null
(cd "$temporary" && sha256sum database.sql.gz uploads.tar.gz > SHA256SUMS)
chmod 600 "$temporary"/*
mv "$temporary" "$target"
restart
trap - EXIT HUP INT TERM
find "$backup_dir" -mindepth 1 -maxdepth 1 -type d -name 'rythm-*' ! -name '*.partial' -mmin "+$((retention_days * 1440))" -exec rm -rf {} \;
printf '%s\n' "$target"
