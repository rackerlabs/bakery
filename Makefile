#  ___                        _  ____      _
# |  _ \ ___  _   _ _ __   __| |/ ___|__ _| | _____
# | |_) / _ \| | | | '_ \ / _` | |   / _` | |/ / _ \
# |  __/ (_) | |_| | | | | (_| | |__| (_| |   <  __/
# |_|   \___/ \__,_|_| |_|\__,_|\____\__,_|_|\_\___|
#
.PHONY: help install dev-install test lint format clean run-api run-worker db-init

help:
	@echo "Available commands:"
	@echo "  make install      - Install production dependencies"
	@echo "  make dev-install  - Install development dependencies"
	@echo "  make test         - Run Bakery tests"
	@echo "  make lint         - Run linters (ruff, mypy)"
	@echo "  make format       - Format code with black"
	@echo "  make clean        - Clean generated files"
	@echo "  make run-api      - Run the Bakery API locally"
	@echo "  make run-worker   - Run the Bakery worker locally"
	@echo "  make db-init      - Run Bakery database migrations"

install:
	pip install .

dev-install:
	pip install -e ".[dev]"

test:
	pytest -m "not integration" tests/ -v --cov=bakery --cov-report=html

lint:
	ruff check bakery shared tests
	mypy bakery shared

format:
	black bakery shared tests
	ruff check --fix bakery shared tests

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build dist .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache

run-api:
	uvicorn bakery.main:app --reload --host 0.0.0.0 --port 8000

run-worker:
	python -m bakery.worker

db-init:
	python -m bakery.db_init
