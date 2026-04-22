SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

UV ?= uv
APP ?= webapp
HOST ?= 127.0.0.1
PORT ?= 8000
COMPOSE ?= docker compose
PYTEST_ARGS ?=
RUFF_ARGS ?=
DEMO_STEP_DELAY ?= 4
DEMO_TYPE_DELAY ?= 0.16
DEMO_FINAL_DELAY ?= 18
DEMO_INITIAL_DELAY ?= 4
DEMO_CHUNK_SIZE ?= 12
DEMO_CHUNK_DELAY ?= 0.32
SHORT_DEMO_STEP_DELAY ?= 1
SHORT_DEMO_TYPE_DELAY ?= 0.05
SHORT_DEMO_FINAL_DELAY ?= 3
SHORT_DEMO_INITIAL_DELAY ?= 1.2
SHORT_DEMO_CHUNK_SIZE ?= 18
SHORT_DEMO_CHUNK_DELAY ?= 0.1
VIDEO_OUTPUT_DIR ?= .pytest_artifacts/e2e/videos
SHORT_VIDEO_OUTPUT_DIR ?= .pytest_artifacts/e2e/videos/short
EXTENSIONS_VIDEO_OUTPUT_DIR ?= .pytest_artifacts/e2e/videos/extensions
VIDEO_FPS ?= 15
VIDEO_CASE ?=
CHAT_WEB_DIR ?= apps/chat_web

.PHONY: help install sync dev run doctor lint fmt-check fmt fix test test-unit test-integration test-e2e test-e2e-extensions test-e2e-extensions-demo test-e2e-extensions-video-pack test-e2e-openai test-e2e-openai-demo test-e2e-openai-demo-record test-e2e-openai-video-pack test-e2e-openai-short-demo test-e2e-openai-short-demo-record test-e2e-openai-short-video-pack chat-web-install chat-web-dev chat-web-test chat-web-build extension-check extension-scaffold docs-check check check-all require-docker docker-up docker-down docker-logs clean bd-check bd-import bd-flush bd-session-close bd-recover-from-jsonl

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
	@chromium_bin="$${E2E_CHROMIUM_BINARY:-$$(command -v chromium || command -v chromium-browser || command -v google-chrome || true)}"; \
	if [ -n "$$chromium_bin" ]; then \
		echo "chromium: $$($$chromium_bin --version 2>/dev/null | head -n 1 || echo "$$chromium_bin")"; \
		if "$$chromium_bin" --headless --disable-gpu --no-sandbox --dump-dom about:blank >/dev/null 2>&1; then \
			echo "chromium headless: ok"; \
		else \
			echo "chromium headless: failed"; \
		fi; \
	else \
		echo "chromium: unavailable"; \
		echo "chromium headless: unavailable"; \
	fi
	@echo "ffmpeg: $$(ffmpeg -version 2>/dev/null | head -n 1 || echo unavailable)"
	@echo "ffprobe: $$(ffprobe -version 2>/dev/null | head -n 1 || echo unavailable)"
	@if command -v xwininfo >/dev/null 2>&1 && command -v xprop >/dev/null 2>&1 && [ -n "$${DISPLAY:-}" ]; then \
		echo "x11 window capture: ok"; \
	else \
		echo "x11 window capture: unavailable"; \
	fi
	@echo "DISPLAY: $${DISPLAY:-missing}"
	@echo "chromedriver override: $${E2E_CHROMEDRIVER_PATH:-auto (Selenium Manager)}"
	@if [ -n "$$OPENAI_API_KEY" ]; then echo "OPENAI_API_KEY: present"; else echo "OPENAI_API_KEY: missing"; fi
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

test-e2e: ## Run deterministic Selenium browser tests
	$(UV) run --all-packages pytest tests/e2e -m "e2e and not openai_smoke and not openai_video_demo and not openai_short_video_demo and not extension_video_demo" $(PYTEST_ARGS)

test-e2e-extensions: ## Run deterministic Selenium tests for extension switching
	$(UV) run --all-packages pytest tests/e2e -m "extensions_e2e and not extension_video_demo" $(PYTEST_ARGS)

test-e2e-extensions-demo: ## Run visible extension demo with cloud OpenAI selector
	@bash -lc 'export PATH="$$HOME/.local/bin:$$PATH"; \
	export E2E_OPENAI_SMOKE=1; \
	export E2E_HEADLESS=0; \
	export E2E_DEMO_MODE=1; \
	export E2E_DEMO_INITIAL_DELAY_SECONDS="$(SHORT_DEMO_INITIAL_DELAY)"; \
	export E2E_DEMO_STEP_DELAY_SECONDS="$(SHORT_DEMO_STEP_DELAY)"; \
	export E2E_DEMO_TYPE_DELAY_SECONDS="$(SHORT_DEMO_TYPE_DELAY)"; \
	export E2E_DEMO_FINAL_DELAY_SECONDS="$(SHORT_DEMO_FINAL_DELAY)"; \
	export E2E_DEMO_CHUNK_SIZE="$(SHORT_DEMO_CHUNK_SIZE)"; \
	export E2E_DEMO_CHUNK_DELAY_SECONDS="$(SHORT_DEMO_CHUNK_DELAY)"; \
	$(UV) run --all-packages pytest \
	tests/e2e/test_web_chat_selenium.py::test_extensions_video_selector_overview \
	-vv -s $(PYTEST_ARGS)'

test-e2e-extensions-video-pack: ## Record the extension mini-pack with cloud OpenAI selector (4 scenarios)
	@bash -lc 'export PATH="$$HOME/.local/bin:$$PATH"; \
	export E2E_OPENAI_SMOKE=1; \
	export E2E_HEADLESS=0; \
	export E2E_DEMO_MODE=1; \
	export E2E_RECORD_VIDEO=1; \
	export E2E_DEMO_INITIAL_DELAY_SECONDS="$(SHORT_DEMO_INITIAL_DELAY)"; \
	export E2E_DEMO_STEP_DELAY_SECONDS="$(SHORT_DEMO_STEP_DELAY)"; \
	export E2E_DEMO_TYPE_DELAY_SECONDS="$(SHORT_DEMO_TYPE_DELAY)"; \
	export E2E_DEMO_FINAL_DELAY_SECONDS="$(SHORT_DEMO_FINAL_DELAY)"; \
	export E2E_DEMO_CHUNK_SIZE="$(SHORT_DEMO_CHUNK_SIZE)"; \
	export E2E_DEMO_CHUNK_DELAY_SECONDS="$(SHORT_DEMO_CHUNK_DELAY)"; \
	export E2E_VIDEO_OUTPUT_DIR="$(EXTENSIONS_VIDEO_OUTPUT_DIR)"; \
	export E2E_VIDEO_FPS="$(VIDEO_FPS)"; \
	video_case_args=(); \
	if [ -n "$(VIDEO_CASE)" ]; then \
		video_case_args=(-k "$(VIDEO_CASE)"); \
	fi; \
	$(UV) run --all-packages pytest tests/e2e \
	-m "extension_video_demo" "$${video_case_args[@]}" -vv -s $(PYTEST_ARGS)'

test-e2e-openai: ## Run optional real OpenAI browser smoke
	@bash -lc 'export PATH="$$HOME/.local/bin:$$PATH"; \
	export E2E_OPENAI_SMOKE=1; \
	$(UV) run --all-packages pytest tests/e2e -m "openai_smoke" $(PYTEST_ARGS)'

test-e2e-openai-demo: ## Run visible OpenAI Selenium demo with lecture-friendly pauses
	@bash -lc 'export PATH="$$HOME/.local/bin:$$PATH"; \
	export E2E_OPENAI_SMOKE=1; \
	export E2E_HEADLESS=0; \
	export E2E_DEMO_MODE=1; \
	export E2E_DEMO_INITIAL_DELAY_SECONDS=$(DEMO_INITIAL_DELAY); \
	export E2E_DEMO_STEP_DELAY_SECONDS=$(DEMO_STEP_DELAY); \
	export E2E_DEMO_TYPE_DELAY_SECONDS=$(DEMO_TYPE_DELAY); \
	export E2E_DEMO_FINAL_DELAY_SECONDS=$(DEMO_FINAL_DELAY); \
	export E2E_DEMO_CHUNK_SIZE=$(DEMO_CHUNK_SIZE); \
	export E2E_DEMO_CHUNK_DELAY_SECONDS=$(DEMO_CHUNK_DELAY); \
	$(UV) run --all-packages pytest \
	tests/e2e/test_web_chat_selenium.py::test_openai_video_preset_overview \
	-vv -s $(PYTEST_ARGS)'

test-e2e-openai-demo-record: ## Run visible OpenAI Selenium demo, slow and recorded to MP4
	@bash -lc 'export PATH="$$HOME/.local/bin:$$PATH"; \
	export E2E_OPENAI_SMOKE=1; \
	export E2E_HEADLESS=0; \
	export E2E_DEMO_MODE=1; \
	export E2E_RECORD_VIDEO=1; \
	export E2E_DEMO_INITIAL_DELAY_SECONDS="$(DEMO_INITIAL_DELAY)"; \
	export E2E_DEMO_STEP_DELAY_SECONDS="$(DEMO_STEP_DELAY)"; \
	export E2E_DEMO_TYPE_DELAY_SECONDS="$(DEMO_TYPE_DELAY)"; \
	export E2E_DEMO_FINAL_DELAY_SECONDS="$(DEMO_FINAL_DELAY)"; \
	export E2E_DEMO_CHUNK_SIZE="$(DEMO_CHUNK_SIZE)"; \
	export E2E_DEMO_CHUNK_DELAY_SECONDS="$(DEMO_CHUNK_DELAY)"; \
	export E2E_VIDEO_OUTPUT_DIR="$(VIDEO_OUTPUT_DIR)"; \
	export E2E_VIDEO_FPS="$(VIDEO_FPS)"; \
	$(UV) run --all-packages pytest \
	tests/e2e/test_web_chat_selenium.py::test_openai_video_preset_overview \
	-vv -s $(PYTEST_ARGS)'

test-e2e-openai-video-pack: ## Record the full slow OpenAI Selenium video pack (5 scenarios)
	@bash -lc 'export PATH="$$HOME/.local/bin:$$PATH"; \
	export E2E_OPENAI_SMOKE=1; \
	export E2E_HEADLESS=0; \
	export E2E_DEMO_MODE=1; \
	export E2E_RECORD_VIDEO=1; \
	export E2E_DEMO_INITIAL_DELAY_SECONDS="$(DEMO_INITIAL_DELAY)"; \
	export E2E_DEMO_STEP_DELAY_SECONDS="$(DEMO_STEP_DELAY)"; \
	export E2E_DEMO_TYPE_DELAY_SECONDS="$(DEMO_TYPE_DELAY)"; \
	export E2E_DEMO_FINAL_DELAY_SECONDS="$(DEMO_FINAL_DELAY)"; \
	export E2E_DEMO_CHUNK_SIZE="$(DEMO_CHUNK_SIZE)"; \
	export E2E_DEMO_CHUNK_DELAY_SECONDS="$(DEMO_CHUNK_DELAY)"; \
	export E2E_VIDEO_OUTPUT_DIR="$(VIDEO_OUTPUT_DIR)"; \
	export E2E_VIDEO_FPS="$(VIDEO_FPS)"; \
	video_case_args=(); \
	if [ -n "$(VIDEO_CASE)" ]; then \
		video_case_args=(-k "$(VIDEO_CASE)"); \
	fi; \
	$(UV) run --all-packages pytest tests/e2e \
	-m "openai_video_demo" "$${video_case_args[@]}" -vv -s $(PYTEST_ARGS)'

test-e2e-openai-short-demo: ## Run visible short OpenAI Selenium demo with compact pacing
	@bash -lc 'export PATH="$$HOME/.local/bin:$$PATH"; \
	export E2E_OPENAI_SMOKE=1; \
	export E2E_HEADLESS=0; \
	export E2E_DEMO_MODE=1; \
	export E2E_DEMO_INITIAL_DELAY_SECONDS="$(SHORT_DEMO_INITIAL_DELAY)"; \
	export E2E_DEMO_STEP_DELAY_SECONDS="$(SHORT_DEMO_STEP_DELAY)"; \
	export E2E_DEMO_TYPE_DELAY_SECONDS="$(SHORT_DEMO_TYPE_DELAY)"; \
	export E2E_DEMO_FINAL_DELAY_SECONDS="$(SHORT_DEMO_FINAL_DELAY)"; \
	export E2E_DEMO_CHUNK_SIZE="$(SHORT_DEMO_CHUNK_SIZE)"; \
	export E2E_DEMO_CHUNK_DELAY_SECONDS="$(SHORT_DEMO_CHUNK_DELAY)"; \
	$(UV) run --all-packages pytest \
	tests/e2e/test_web_chat_selenium.py::test_openai_short_video_preset_overview \
	-vv -s $(PYTEST_ARGS)'

test-e2e-openai-short-demo-record: ## Run visible short OpenAI Selenium demo and record one compact MP4
	@bash -lc 'export PATH="$$HOME/.local/bin:$$PATH"; \
	export E2E_OPENAI_SMOKE=1; \
	export E2E_HEADLESS=0; \
	export E2E_DEMO_MODE=1; \
	export E2E_RECORD_VIDEO=1; \
	export E2E_DEMO_INITIAL_DELAY_SECONDS="$(SHORT_DEMO_INITIAL_DELAY)"; \
	export E2E_DEMO_STEP_DELAY_SECONDS="$(SHORT_DEMO_STEP_DELAY)"; \
	export E2E_DEMO_TYPE_DELAY_SECONDS="$(SHORT_DEMO_TYPE_DELAY)"; \
	export E2E_DEMO_FINAL_DELAY_SECONDS="$(SHORT_DEMO_FINAL_DELAY)"; \
	export E2E_DEMO_CHUNK_SIZE="$(SHORT_DEMO_CHUNK_SIZE)"; \
	export E2E_DEMO_CHUNK_DELAY_SECONDS="$(SHORT_DEMO_CHUNK_DELAY)"; \
	export E2E_VIDEO_OUTPUT_DIR="$(SHORT_VIDEO_OUTPUT_DIR)"; \
	export E2E_VIDEO_FPS="$(VIDEO_FPS)"; \
	$(UV) run --all-packages pytest \
	tests/e2e/test_web_chat_selenium.py::test_openai_short_video_preset_overview \
	-vv -s $(PYTEST_ARGS)'

test-e2e-openai-short-video-pack: ## Record the compact OpenAI Selenium short video pack (8 scenarios)
	@bash -lc 'export PATH="$$HOME/.local/bin:$$PATH"; \
	export E2E_OPENAI_SMOKE=1; \
	export E2E_HEADLESS=0; \
	export E2E_DEMO_MODE=1; \
	export E2E_RECORD_VIDEO=1; \
	export E2E_DEMO_INITIAL_DELAY_SECONDS="$(SHORT_DEMO_INITIAL_DELAY)"; \
	export E2E_DEMO_STEP_DELAY_SECONDS="$(SHORT_DEMO_STEP_DELAY)"; \
	export E2E_DEMO_TYPE_DELAY_SECONDS="$(SHORT_DEMO_TYPE_DELAY)"; \
	export E2E_DEMO_FINAL_DELAY_SECONDS="$(SHORT_DEMO_FINAL_DELAY)"; \
	export E2E_DEMO_CHUNK_SIZE="$(SHORT_DEMO_CHUNK_SIZE)"; \
	export E2E_DEMO_CHUNK_DELAY_SECONDS="$(SHORT_DEMO_CHUNK_DELAY)"; \
	export E2E_VIDEO_OUTPUT_DIR="$(SHORT_VIDEO_OUTPUT_DIR)"; \
	export E2E_VIDEO_FPS="$(VIDEO_FPS)"; \
	video_case_args=(); \
	if [ -n "$(VIDEO_CASE)" ]; then \
		video_case_args=(-k "$(VIDEO_CASE)"); \
	fi; \
	$(UV) run --all-packages pytest tests/e2e \
	-m "openai_short_video_demo" "$${video_case_args[@]}" -vv -s $(PYTEST_ARGS)'

chat-web-install: ## Install Next.js chat shell dependencies
	cd $(CHAT_WEB_DIR) && npm install

chat-web-dev: ## Run the Next.js chat shell in dev mode
	cd $(CHAT_WEB_DIR) && npm run dev

chat-web-test: ## Run frontend tests for the Next.js chat shell
	cd $(CHAT_WEB_DIR) && npm test

chat-web-build: ## Build the Next.js chat shell for production
	cd $(CHAT_WEB_DIR) && npm run build

docs-check: ## Validate baseline docstring coverage (module + public callables)
	$(UV) run python scripts/check_doc_coverage.py

extension-check: ## Validate one declarative extension bundle (usage: make extension-check EXT=study_planner)
	@if [ -z "$(EXT)" ]; then echo "Usage: make extension-check EXT=<alias-or-path>"; exit 1; fi
	$(UV) run --all-packages python -m agent_core.extension_check $(EXT)

extension-scaffold: ## Generate a new declarative scaffold (allocation or transportation)
	@if [ -z "$(EXT)" ] || [ -z "$(TITLE)" ] || [ -z "$(RESOURCE_LABEL_RU)" ]; then \
		echo 'Usage (allocation): make extension-scaffold EXT=<alias> TITLE="..." RESOURCE_LABEL_RU="..." ENTITY_SINGULAR_RU="..." ENTITY_PLURAL_RU="..." [SET_SYMBOL=ITEMS]'; \
		echo 'Usage (transportation): make extension-scaffold EXT=<alias> TITLE="..." TEMPLATE_FAMILY=transportation RESOURCE_LABEL_RU="..." ROW_ENTITY_SINGULAR_RU="..." ROW_ENTITY_PLURAL_RU="..." COL_ENTITY_SINGULAR_RU="..." COL_ENTITY_PLURAL_RU="..." [ROW_SET_SYMBOL=ORIGINS] [COL_SET_SYMBOL=DESTINATIONS]'; \
		exit 1; \
	fi
	@bash -lc 'args=("$(EXT)" --title "$(TITLE)" --resource-label-ru "$(RESOURCE_LABEL_RU)" --template-family "$(if $(TEMPLATE_FAMILY),$(TEMPLATE_FAMILY),allocation)"); \
	if [ "$(if $(TEMPLATE_FAMILY),$(TEMPLATE_FAMILY),allocation)" = "transportation" ]; then \
		if [ -z "$(ROW_ENTITY_SINGULAR_RU)" ] || [ -z "$(ROW_ENTITY_PLURAL_RU)" ] || [ -z "$(COL_ENTITY_SINGULAR_RU)" ] || [ -z "$(COL_ENTITY_PLURAL_RU)" ]; then \
			echo "Usage (transportation): make extension-scaffold EXT=<alias> TITLE=\"...\" TEMPLATE_FAMILY=transportation RESOURCE_LABEL_RU=\"...\" ROW_ENTITY_SINGULAR_RU=\"...\" ROW_ENTITY_PLURAL_RU=\"...\" COL_ENTITY_SINGULAR_RU=\"...\" COL_ENTITY_PLURAL_RU=\"...\" [ROW_SET_SYMBOL=ORIGINS] [COL_SET_SYMBOL=DESTINATIONS]"; \
			exit 1; \
		fi; \
		args+=(--row-entity-singular-ru "$(ROW_ENTITY_SINGULAR_RU)" --row-entity-plural-ru "$(ROW_ENTITY_PLURAL_RU)" --col-entity-singular-ru "$(COL_ENTITY_SINGULAR_RU)" --col-entity-plural-ru "$(COL_ENTITY_PLURAL_RU)" --row-set-symbol "$(if $(ROW_SET_SYMBOL),$(ROW_SET_SYMBOL),ORIGINS)" --col-set-symbol "$(if $(COL_SET_SYMBOL),$(COL_SET_SYMBOL),DESTINATIONS)"); \
	else \
		if [ -z "$(ENTITY_SINGULAR_RU)" ] || [ -z "$(ENTITY_PLURAL_RU)" ]; then \
			echo "Usage (allocation): make extension-scaffold EXT=<alias> TITLE=\"...\" RESOURCE_LABEL_RU=\"...\" ENTITY_SINGULAR_RU=\"...\" ENTITY_PLURAL_RU=\"...\" [SET_SYMBOL=ITEMS]"; \
			exit 1; \
		fi; \
		args+=(--entity-singular-ru "$(ENTITY_SINGULAR_RU)" --entity-plural-ru "$(ENTITY_PLURAL_RU)" --set-symbol "$(if $(SET_SYMBOL),$(SET_SYMBOL),ITEMS)"); \
	fi; \
	$(UV) run --all-packages python -m agent_core.extension_scaffold "$${args[@]}"'

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
	rm -rf .pytest_cache .ruff_cache .pytest_artifacts
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
