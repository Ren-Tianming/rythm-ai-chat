#!/bin/sh
set -eu

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo "Usage: restore.sh /path/to/backup.sql.gz" >&2
  exit 2
fi

project_dir="${RYTHM_PROJECT_DIR:-/opt/rythm-chatbot}"
env_file="${RYTHM_ENV_FILE:-${project_dir}/.env}"
backup_file="$1"

cd "$project_dir"
test -f "$env_file"
gzip -t "$backup_file"
docker compose --env-file "$env_file" stop backend web
docker compose --env-file "$env_file" exec -T db sh -c \
  'dropdb --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
gzip -dc "$backup_file" | docker compose --env-file "$env_file" exec -T db sh -c \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose --env-file "$env_file" up -d backend web
docker compose --env-file "$env_file" exec -T backend alembic upgrade head
