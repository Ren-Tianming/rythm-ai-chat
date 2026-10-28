#!/bin/bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
runtime="$(mktemp -d)"
export COMPOSE_PROJECT_NAME=rythm-smoke
export ENV_FILE="$runtime/test.env"
export RYTHM_PROJECT_DIR="$root" RYTHM_ENV_FILE="$ENV_FILE" RYTHM_BACKUP_DIR="$runtime/backups"
cat > "$ENV_FILE" <<'ENV'
ENVIRONMENT=test
POSTGRES_PASSWORD=smoke-test-only
CHATBOT_PORT=18081
DEEPSEEK_API_KEY=test-only
DEEPSEEK_MODEL=test-only
EMBEDDING_DIMENSIONS=8
ENV
cd "$root"
cleanup() {
  docker compose --env-file "$ENV_FILE" logs --tail 25 || true
  docker compose --env-file "$ENV_FILE" down -v --remove-orphans || true
  rm -rf "$runtime"
}
trap cleanup EXIT
docker compose --env-file "$ENV_FILE" config -q
docker compose --env-file "$ENV_FILE" up -d --build --wait --wait-timeout 180 db backend web
docker compose --env-file "$ENV_FILE" up -d document-worker
worker_id="$(docker compose --env-file "$ENV_FILE" ps -q document-worker)"
test "$(docker inspect --format '{{.State.Running}}' "$worker_id")" = true
curl --fail --retry 5 --retry-delay 1 http://127.0.0.1:18081/api/v1/health/ready
# Test files are never exposed by the web container/static route.
docker compose --env-file "$ENV_FILE" exec -T backend python - seed < scripts/docker-smoke-data.py
curl -s http://127.0.0.1:18081/uploads/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.txt > "$runtime/static-body"
! grep -Fq 'Private ORION backup evidence.' "$runtime/static-body"
"$root/deploy/backup.sh"
backup="$(find "$runtime/backups" -mindepth 1 -maxdepth 1 -type d -name 'rythm-*' ! -name '*.partial' | head -1)"
test -n "$backup"
docker compose --env-file "$ENV_FILE" exec -T backend python - mutate < scripts/docker-smoke-data.py
"$root/deploy/restore.sh" "$backup"
docker compose --env-file "$ENV_FILE" exec -T backend python - assert < scripts/docker-smoke-data.py
curl --fail --retry 5 --retry-delay 1 http://127.0.0.1:18081/api/v1/health/ready
