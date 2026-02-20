.DEFAULT_GOAL := help

.PHONY: help setup dev test lint format migrate migration

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Install all dependencies and apply database migrations
	@echo "Installing backend dependencies..."
	cd backend && uv sync
	@echo "Installing frontend dependencies..."
	cd frontend && npm install
	@echo "Applying database migrations..."
	cd backend && uv run alembic upgrade head

dev: ## Run backend and frontend dev servers concurrently
	@trap 'kill 0' EXIT; \
	cd backend && uv run python -m uvicorn main:app --reload & \
	cd frontend && npm run dev & \
	wait

test: ## Run all backend and frontend tests (sequential, fail-fast)
	@echo "Running backend tests..."
	cd backend && uv run pytest
	@echo "Running frontend tests..."
	cd frontend && npm run test

lint: ## Run all linters and type checks (sequential, fail-fast)
	@echo "Linting backend..."
	cd backend && uv run ruff check .
	@echo "Linting frontend..."
	cd frontend && npm run lint
	@echo "Type-checking frontend..."
	cd frontend && npm run type-check

format: ## Auto-format backend code
	cd backend && uv run ruff check --fix . && uv run ruff format .

migrate: ## Apply pending database migrations
	cd backend && uv run alembic upgrade head

migration: ## Create a new migration (usage: make migration msg="description")
ifndef msg
	$(error msg is required. Usage: make migration msg="description of changes")
endif
	cd backend && uv run alembic revision --autogenerate -m "$(msg)"
