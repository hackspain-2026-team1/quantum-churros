.DEFAULT_GOAL := help

COMPOSE := docker compose -f compose.yaml -f compose.dev.yaml

.PHONY: dev
dev: ## Build and start the complete development stack
	$(COMPOSE) up --build --watch

.PHONY: up
up: ## Start the development stack in the background
	$(COMPOSE) up --build -d

.PHONY: down
down: ## Stop services without deleting data
	$(COMPOSE) down

.PHONY: logs
logs: ## Follow service logs
	$(COMPOSE) logs -f $(service)

.PHONY: status
status: ## Show service and health status
	$(COMPOSE) ps

.PHONY: test
test: test-engine test-backend test-frontend ## Run every test suite

.PHONY: test-engine
test-engine: ## Run scoring engine tests
	uv run --package xray-engine pytest engine/tests

.PHONY: test-backend
test-backend: ## Run API tests
	uv run --package quantum-churros-api pytest backend/tests

.PHONY: test-frontend
test-frontend: ## Type-check and test the frontend
	cd frontend && bun run check && bun run test

.PHONY: score
score: ## Score the dataset mounted under data/raw
	uv run --package xray-engine xray-score data/raw --output artifacts/scores.parquet

.PHONY: db-migrate
db-migrate: ## Apply pending Alembic migrations
	uv run --package quantum-churros-api alembic -c backend/alembic.ini upgrade head

.PHONY: data-extract
data-extract: ## Extract the local challenge archive into the ignored data directory
	unzip -j -n "$(archive)" 'output/*' -d data/raw

.PHONY: help
help: ## Show available targets
	@rg '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST)
