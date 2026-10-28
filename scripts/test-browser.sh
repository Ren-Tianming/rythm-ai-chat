#!/bin/bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
: "${TEST_DATABASE_URL:?Use a disposable PostgreSQL + pgvector test database}"
export DATABASE_URL="$TEST_DATABASE_URL"
export ENVIRONMENT=test
export DEEPSEEK_API_KEY=test-only DEEPSEEK_MODEL=test GROQ_API_KEY=test-only GROQ_MODEL=test
export EMBEDDING_API_KEY=test-only EMBEDDING_DIMENSIONS=8 OCR_LANGUAGES="${OCR_LANGUAGES:-eng}"
export CHAT_PER_MINUTE_LIMIT=100 DAILY_CHAT_LIMIT=1000
export FRONTEND_URL=http://127.0.0.1:5173 CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5173
runtime="$(mktemp -d)"
export UPLOAD_DIR="$runtime/uploads" E2E_MAIL_FILE="$runtime/mail.json" E2E_FIXTURE_DIR="$runtime/fixtures"
python_bin="${PYTHON:-python}"
(cd "$root/backend" && PYTHONPATH=. "$python_bin" tests/create_browser_fixtures.py)
(cd "$root/backend" && exec env PYTHONPATH=. "$python_bin" tests/browser_server.py) > "$runtime/backend.log" 2>&1 &
backend_pid=$!
(cd "$root/frontend" && exec node node_modules/vite/bin/vite.js --host 127.0.0.1) > "$runtime/frontend.log" 2>&1 &
frontend_pid=$!
cleanup() {
  kill "$backend_pid" "$frontend_pid" 2>/dev/null || true
  wait "$backend_pid" "$frontend_pid" 2>/dev/null || true
  cat "$runtime/backend.log" "$runtime/frontend.log"
  rm -rf "$runtime"
}
trap cleanup EXIT
for attempt in $(seq 1 100); do
  if curl --noproxy '*' -fsS http://127.0.0.1:8000/api/v1/health/live >/dev/null 2>&1 && curl --noproxy '*' -fsS http://127.0.0.1:5173 >/dev/null 2>&1; then break; fi
  sleep .2
done
cd "$root/frontend"
npx playwright test
