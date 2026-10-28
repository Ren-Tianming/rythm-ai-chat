#!/bin/sh
set -eu

if [ "$#" -ne 1 ] || [ ! -d "$1" ]; then
  echo "Usage: restore.sh /absolute/path/to/rythm-YYYYMMDDTHHMMSSZ" >&2
  exit 2
fi
backup_dir="$(cd "$1" && pwd)"
project_dir="${RYTHM_PROJECT_DIR:-/opt/rythm-chatbot}"
env_file="${RYTHM_ENV_FILE:-${project_dir}/.env}"
(cd "$backup_dir" && sha256sum -c SHA256SUMS)
gzip -t "$backup_dir/database.sql.gz"
tar -tzf "$backup_dir/uploads.tar.gz" >/dev/null
cd "$project_dir"
test -f "$env_file"
docker compose --env-file "$env_file" stop backend document-worker web
docker compose --env-file "$env_file" exec -T db sh -c \
  'dropdb --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
# Materialize the SQL so decompression errors cannot be hidden by a shell pipeline.
sql_file="$(mktemp)"
trap 'rm -f "$sql_file"' EXIT HUP INT TERM
gzip -dc "$backup_dir/database.sql.gz" > "$sql_file"
docker compose --env-file "$env_file" exec -T db sh -c \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$sql_file"
# Restore only a trusted, checksum-verified operator backup; never user-provided tar files.
docker compose --env-file "$env_file" run --rm --no-deps -T --entrypoint sh backend -c \
  'find /app/uploads -mindepth 1 -maxdepth 1 -type f -delete && tar -xzf - -C /app/uploads --no-same-owner' < "$backup_dir/uploads.tar.gz"
docker compose --env-file "$env_file" up -d backend document-worker web
