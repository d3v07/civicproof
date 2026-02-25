SHELL := /bin/bash
.DEFAULT_GOAL := help

.PHONY: help dev-up dev-down dev-logs lint fmt test test-all migrate migrate-new seed clean

help:
	@echo "CivicProof development targets"
	@echo ""
	@echo "  dev-up       Start local dev stack (Postgres, Redis, MinIO, OpenSearch)"
	@echo "  dev-down     Tear down local dev stack and remove volumes"
	@echo "  dev-logs     Tail dev stack logs"
	@echo "  lint         Run ruff check + mypy"
	@echo "  fmt          Format code with ruff"
	@echo "  test         Run unit tests with coverage"
	@echo "  test-all     Run all tests (unit + integration + contract + e2e)"
	@echo "  migrate      Apply pending Alembic migrations"
	@echo "  migrate-new  Generate new Alembic migration (pass MSG='<description>')"
	@echo "  seed         Seed initial data sources into Postgres"
	@echo "  clean        Remove __pycache__ and .pyc files"

dev-up:
	docker compose -f docker-compose.dev.yml up -d

dev-down:
	docker compose -f docker-compose.dev.yml down -v

dev-logs:
	docker compose -f docker-compose.dev.yml logs -f

lint:
	ruff check . && mypy packages/ services/ --ignore-missing-imports

fmt:
	ruff format .

test:
	pytest tests/unit/ -v --cov=packages --cov=services --cov-report=term-missing

test-all:
	pytest tests/ -v

migrate:
	cd packages/common && alembic upgrade head

migrate-new:
	cd packages/common && alembic revision --autogenerate -m "$(MSG)"

seed:
	bash scripts/seed_data.sh

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; find . -name "*.pyc" -delete 2>/dev/null; true
