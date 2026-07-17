.PHONY: dev up down test lint build migrate

dev:
	docker compose up --build

up:
	docker compose up -d --build

down:
	docker compose down

test:
	cd backend && pytest

lint:
	cd backend && ruff check .
	cd frontend && npm run build

build:
	docker compose build

migrate:
	docker compose run --rm backend alembic upgrade head
