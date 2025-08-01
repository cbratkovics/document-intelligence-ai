.PHONY: help install dev test lint format clean docker-build docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  make install      Install dependencies"
	@echo "  make dev          Run development server"
	@echo "  make test         Run tests"
	@echo "  make lint         Run linting"
	@echo "  make format       Format code"
	@echo "  make clean        Clean up temporary files"
	@echo "  make docker-build Build Docker image"
	@echo "  make docker-up    Start Docker services"
	@echo "  make docker-down  Stop Docker services"

install:
	pip install -r requirements.txt

dev:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

test-coverage:
	pytest tests/ --cov=src --cov-report=html --cov-report=term

lint:
	pip install flake8 black isort mypy
	flake8 src/ tests/
	black --check src/ tests/
	isort --check-only src/ tests/
	mypy src/

format:
	pip install black isort
	black src/ tests/
	isort src/ tests/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov
	rm -rf .mypy_cache

docker-build:
	docker build -f docker/Dockerfile -t document-intelligence-ai:latest .

docker-up:
	docker-compose -f docker/docker-compose.yml up -d

docker-down:
	docker-compose -f docker/docker-compose.yml down

docker-logs:
	docker-compose -f docker/docker-compose.yml logs -f

docker-shell:
	docker-compose -f docker/docker-compose.yml exec app /bin/bash

# Development database commands
db-reset:
	docker-compose -f docker/docker-compose.yml down -v
	docker-compose -f docker/docker-compose.yml up -d chromadb redis

# Quick start for development
quickstart: install
	cp .env.example .env
	@echo "Please edit .env and add your API keys"
	@echo "Then run 'make dev' to start the development server"