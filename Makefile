SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

UV ?= uv
APP ?= webapp
HOST ?= 127.0.0.1
PORT ?= 8000
COMPOSE ?= docker compose
PYTEST_ARGS ?=
RUFF_ARGS ?=

.PHONY: help install sync dev run doctor lint fmt-check fmt fix test test-unit test-integration docs-check check check-all require-docker docker-up docker-down docker-logs clean bd-check bd-import bd-flush bd-session-close bd-recover-from-jsonl

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "; printf "\nUsage:\n  make <target>\n\nTargets:\n"} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install workspace dependencies
	$(UV) sync --all-packages --group dev

sync: install ## Alias for install

dev: ## Run dev server with autoreload
	$(UV) run --package $(APP) uvicorn webapp.main:app --reload --host $(HOST) --port $(PORT)

run: ## Run server without autoreload
	$(UV) run --package $(APP) uvicorn webapp.main:app --host $(HOST) --port $(PORT)

doctor: ## Show local toolchain and docker availability
	@echo "python: $$(python3 --version 2>&1 || echo unavailable)"
	@echo "uv: $$( $(UV) --version 2>&1 || echo unavailable )"
	@echo "make: $$(make --version | head -n 1 2>/dev/null || echo unavailable)"
	@docker_version="$$(docker --version 2>/dev/null || true)"; \
	if [ -n "$$docker_version" ] && docker info >/dev/null 2>&1; then \
		echo "docker: $$docker_version"; \
		echo "docker compose: $$($(COMPOSE) version 2>/dev/null | head -n 1)"; \
	else \
		echo "docker: unavailable (not installed or not integrated in current environment)"; \
		echo "docker compose: unavailable"; \
	fi

lint: ## Run Ruff lint checks
	$(UV) run --all-packages ruff check . $(RUFF_ARGS)

fmt-check: ## Check code formatting (non-mutating)
	$(UV) run --all-packages ruff format --check .

fmt: ## Format code with Ruff formatter
	$(UV) run --all-packages ruff format .

fix: ## Apply lint fixes and formatting
	$(UV) run --all-packages ruff check . --fix
	$(MAKE) fmt

test: ## Run full test suite
	$(UV) run --all-packages pytest $(PYTEST_ARGS)

test-unit: ## Run unit tests only
	$(UV) run --all-packages pytest tests/unit $(PYTEST_ARGS)

test-integration: ## Run integration tests only
	$(UV) run --all-packages pytest tests/integration $(PYTEST_ARGS)

docs-check: ## Validate baseline docstring coverage (module + public callables)
	$(UV) run python scripts/check_doc_coverage.py

check: lint test ## Fast quality gate (lint + tests)

check-all: fmt-check check docs-check ## Strict quality gate (format + lint + tests + docs)

require-docker: ## Verify docker availability
	@if ! docker info >/dev/null 2>&1; then \
		echo "Error: docker is not available in this environment."; \
		echo "Install Docker or enable Docker Desktop WSL integration and retry."; \
		exit 1; \
	fi

docker-up: require-docker ## Build and run dockerized app
	$(COMPOSE) up --build

docker-down: require-docker ## Stop dockerized app
	$(COMPOSE) down

docker-logs: require-docker ## Follow webapp container logs
	$(COMPOSE) logs -f webapp

clean: ## Remove caches only (safe cleanup)
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

bd-check: ## Validate safe beads policy (version/config/doctor)
	./scripts/bd_policy_check.sh

bd-import: ## Validate or bootstrap beads DB availability (safe start step)
	./scripts/bd_import_safe.sh

bd-flush: ## Export beads issues to .beads/issues.jsonl with safety checks
	./scripts/bd_flush_safe.sh

bd-session-close: ## Run beads pre-push safety sequence (check + flush)
	./scripts/bd_session_close.sh

bd-recover-from-jsonl: ## Rebuild beads DB from .beads/issues.jsonl (recovery)
	./scripts/bd_recover_from_jsonl.sh
