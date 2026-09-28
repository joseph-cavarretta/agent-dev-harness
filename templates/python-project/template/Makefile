.PHONY: install dev-install test lint format type-check check

install:
	uv sync

dev-install:
	uv sync
	uv run pre-commit install

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

type-check:
	uv run mypy src tests

# ruff, format check, mypy and pytest in one run, failures only.
check:
	ah-check
