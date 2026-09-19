.DEFAULT_GOAL := help

COMPOSE := docker compose -f compose.yaml -f compose.dev.yaml
XRAY_DATA ?= data/raw
XRAY_BUNDLE ?= frontend/static/data/v1
XRAY_OUT ?= artifacts

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

.PHONY: test-engine-data
test-engine-data: ## Run the engine tests that need the real dataset (XRAY_DATA=<folder>)
	XRAY_DATA=$(XRAY_DATA) uv run --package xray-engine pytest engine/tests -m dataset

.PHONY: fit-reference
fit-reference: ## Measure and freeze params/reference_v1.json from XRAY_DATA
	uv run --package xray-engine xray-score fit-reference $(XRAY_DATA) --out params/reference_v1.json

.PHONY: predict
predict: ## Score every group and company of XRAY_DATA (any folder with the 8 CSVs) into XRAY_OUT
	uv run --package xray-engine xray-score predict $(XRAY_DATA) --out $(XRAY_OUT)

.PHONY: score
score: predict ## Alias of predict

.PHONY: validate
validate: ## Run the label-free validation suite and write XRAY_OUT/validation.json
	uv run --package xray-engine xray-score validate $(XRAY_DATA) --out $(XRAY_OUT)/validation.json

.PHONY: export
export: ## Score XRAY_DATA and write the static JSON bundle to XRAY_BUNDLE
	uv run --package xray-engine xray-score predict $(XRAY_DATA) --out $(XRAY_OUT) --export-dir $(XRAY_BUNDLE)

.PHONY: db-migrate
db-migrate: ## Apply pending Alembic migrations
	$(COMPOSE) exec api uv run --locked --package quantum-churros-api alembic -c backend/alembic.ini upgrade head

.PHONY: db-seed-dry-run
db-seed-dry-run: ## Validate source files and print their immutable dataset hash
	uv run --package quantum-churros-api xray-db ingest data/raw --dry-run

.PHONY: db-seed
db-seed: ## Idempotently ingest the challenge dataset into PostgreSQL
	$(COMPOSE) exec api uv run --locked --package quantum-churros-api xray-db ingest /data/raw

.PHONY: db-classify
db-classify: ## Classify companies into industry archetypes for the mounted dataset
	$(COMPOSE) exec api uv run --locked --package quantum-churros-api xray-db classify /data/raw

.PHONY: data-extract
data-extract: ## Extract the local challenge archive into the ignored data directory
	unzip -j -n "$(archive)" 'output/*' -d data/raw

NO_MOCKS_PATTERN := COMP_0680|Velasco|4,1 meses|74\.5|[Cc]at[Bb]oost|SHAP

.PHONY: no-mocks
no-mocks: ## Fail when demo literals or retired model copy remain in shipped code
	@if grep -rnIE '$(NO_MOCKS_PATTERN)' frontend/src backend/app; then \
		echo 'no-mocks: demo literals found in shipped code (listed above)'; exit 1; \
	else \
		echo 'no-mocks: clean'; \
	fi

.PHONY: help
help: ## Show available targets
	@rg '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST)
