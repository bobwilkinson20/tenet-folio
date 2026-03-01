.DEFAULT_GOAL := help

.PHONY: help setup dev dev-paper dev-test test lint format migrate migration

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Install all dependencies and apply database migrations
	@echo "Installing backend dependencies..."
	cd backend && uv sync
	@echo "Installing frontend dependencies..."
	cd frontend && npm install
	@echo "Applying database migrations..."
	cd backend && uv run alembic upgrade head

BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 5173

dev: ## Run backend and frontend dev servers concurrently
	@trap 'kill 0' EXIT; \
	cd backend && FRONTEND_URL=http://localhost:$(FRONTEND_PORT) \
	  uv run python -m uvicorn main:app --reload --port $(BACKEND_PORT) & \
	cd frontend && VITE_API_URL=http://localhost:$(BACKEND_PORT)/api \
	  npx vite --port $(FRONTEND_PORT) & \
	wait

dev-paper: ## Run dev servers with TENET_PROFILE=paper (ports 8001/5174)
	TENET_PROFILE=paper BACKEND_PORT=8001 FRONTEND_PORT=5174 $(MAKE) dev

dev-test: ## Run dev servers with TENET_PROFILE=test (ports 8002/5175)
	TENET_PROFILE=test BACKEND_PORT=8002 FRONTEND_PORT=5175 $(MAKE) dev

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
