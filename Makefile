.PHONY: help install dev api worker sim web lint typecheck test test-unit test-integration test-e2e test-chaos eval check migrate bootstrap up down logs fault clear-faults demo

PY ?= .venv/bin/python
ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python
endif

help:
	@echo "Sentinel — evidence-driven incident intelligence"
	@echo ""
	@echo "  make install        install backend (uv) + web (npm) dependencies"
	@echo "  make dev            zero-infra stack: API + scheduler + demo shop (SQLite, in-process queue)"
	@echo "  make web            Next.js dashboard on :3000"
	@echo "  make test           unit + integration + chaos tests"
	@echo "  make eval           run the 100+ scenario benchmark → docs/evaluation/latest.md"
	@echo "  make check          lint + typecheck + tests"
	@echo "  make up / down      docker compose full stack (add PROFILES='--profile observability --profile llm')"
	@echo "  make fault          inject a DB pool exhaustion fault into payment-service"
	@echo "  make demo           the 11-step investor demo (docs/demo.md)"

install:
	uv sync --all-extras
	cd web && npm install

dev:
	$(PY) -m sentinel.cli dev

api:
	$(PY) -m sentinel.cli api --reload

worker:
	$(PY) -m sentinel.cli worker

sim:
	$(PY) -m sentinel_sim.cli run

web:
	cd web && npm run dev

lint:
	$(PY) -m ruff check backend simulator tests
	$(PY) -m ruff format --check backend simulator tests || true

fmt:
	$(PY) -m ruff format backend simulator tests
	$(PY) -m ruff check --fix backend simulator tests

typecheck:
	$(PY) -m mypy backend/sentinel --ignore-missing-imports || true

test: test-unit test-integration test-chaos

test-unit:
	$(PY) -m pytest tests/unit -q

test-integration:
	$(PY) -m pytest tests/integration -q

test-chaos:
	$(PY) -m pytest tests/chaos -q

test-e2e:
	SENTINEL_E2E_API=http://localhost:8000 $(PY) -m pytest tests/e2e -q -m e2e

eval:
	$(PY) -m sentinel.cli eval run --name make-eval --report docs/evaluation/latest.md

check: lint test

migrate:
	$(PY) -m sentinel.cli migrate

bootstrap:
	$(PY) -m sentinel.cli bootstrap

up:
	docker compose $(PROFILES) up --build -d

down:
	docker compose --profile observability --profile llm down

logs:
	docker compose logs -f api worker simulator

fault:
	$(PY) -m sentinel.cli fault inject payment-service --type db_pool_exhaustion --duration 180

clear-faults:
	$(PY) -m sentinel.cli fault clear

demo:
	@echo "See docs/demo.md — start 'make dev' and 'make web', then follow the 11 steps."
