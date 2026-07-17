#!/bin/sh
set -eu
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-1}" --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}"
