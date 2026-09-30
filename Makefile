.PHONY: dev test lint format typecheck check docker seed

PORT ?= 8091

dev:
	uv run uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --reload

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy app

check: lint typecheck test

docker:
	docker build -t harbor-desk .

seed:
	uv run python -c "from app.bank.fixture import init_bank; init_bank('data/bank.sqlite')"
