
# API Galaxy — one place for every command you need.
# Run `make` (or `make help`) to see what is available.

SHELL := /bin/bash
PY := .venv/bin/python
PIP := .venv/bin/python -m pip
RUFF := .venv/bin/ruff
API_DIR := apps/api
WEB_DIR := apps/web
PORT_API ?= 8099
PORT_WEB ?= 3000
# The browser calls /api/* on its own origin and Next proxies to this. It has to track
# PORT_API, or `make demo PORT_API=8100` serves a UI pointed at a backend that is not there.
API_URL ?= http://127.0.0.1:$(PORT_API)

.DEFAULT_GOAL := help
.PHONY: help setup setup-api setup-web dev dev-api dev-web build test test-api test-web \
        e2e lint typecheck format demo demo-reset clean doctor check ports stop

help: ## Show this help
	@echo "API Galaxy"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Quick start:  make setup && make demo"

# ----------------------------------------------------------------------------- setup

setup: setup-api setup-web ## Install everything (Python venv + node modules)
	@echo ""
	@echo "Ready. Run 'make demo' to start both servers and open the demo estate."

setup-api: ## Create the Python virtualenv and install the backend
	@command -v uv >/dev/null 2>&1 \
	  && uv venv --python 3.12 .venv \
	  || python3 -m venv .venv
	@command -v uv >/dev/null 2>&1 \
	  && VIRTUAL_ENV=.venv uv pip install -e "$(API_DIR)[dev,png,pdf,keyring]" \
	  || $(PIP) install -e "$(API_DIR)[dev,png,pdf,keyring]"
	@echo "Backend installed."

setup-web: ## Install the web app's dependencies
	@cd $(WEB_DIR) && npm install --no-audit --no-fund
	@echo "Web app installed."

# ------------------------------------------------------------------------------- run

dev: ## Run the API and the web app together (Ctrl-C stops both)
	@echo "API  → http://127.0.0.1:$(PORT_API)/api/docs"
	@echo "Web  → http://127.0.0.1:$(PORT_WEB)"
	@trap 'kill 0' EXIT INT TERM; \
	  $(MAKE) dev-api & \
	  $(MAKE) dev-web & \
	  wait

dev-api: ## Run only the backend
	@$(PY) -m uvicorn api_galaxy.app.main:app \
	  --host 127.0.0.1 --port $(PORT_API) --app-dir $(API_DIR) --reload

dev-web: ## Run only the web app
	@cd $(WEB_DIR) && NEXT_PUBLIC_API_URL=$(API_URL) npm run dev -- --port $(PORT_WEB)

ports: ## Show what is listening on the app's ports
	@for p in $(PORT_API) $(PORT_WEB); do \
	  pid=$$(lsof -ti tcp:$$p 2>/dev/null | tr '\n' ' '); \
	  if [ -n "$$pid" ]; then echo "  port $$p  IN USE by pid $$pid"; \
	  else echo "  port $$p  free"; fi; \
	done

stop: ## Stop any API or web server this project started
	@pkill -f "uvicorn api_galaxy" 2>/dev/null && echo "Stopped the API." || echo "No API running."
	@pkill -f "next dev" 2>/dev/null && echo "Stopped the web app." || echo "No web app running."

demo: ## Start everything and load the bundled NovaCart estate
	@# Check the ports before starting anything. Previously this launched uvicorn, and the
	@# health check then succeeded against whatever was *already* on the port — so it
	@# printed "Demo estate loaded" and failed to bind in the same breath.
	@busy=""; \
	for p in $(PORT_API) $(PORT_WEB); do \
	  if lsof -ti tcp:$$p >/dev/null 2>&1; then busy="$$busy $$p"; fi; \
	done; \
	if [ -n "$$busy" ]; then \
	  echo "Port(s)$$busy are already in use."; \
	  echo ""; \
	  $(MAKE) --no-print-directory ports; \
	  echo ""; \
	  echo "Either stop them:      make stop"; \
	  echo "or use other ports:    make demo PORT_API=8100 PORT_WEB=3100"; \
	  exit 1; \
	fi
	@echo "Starting API on :$(PORT_API)…"
	@$(PY) -m uvicorn api_galaxy.app.main:app \
	  --host 127.0.0.1 --port $(PORT_API) --app-dir $(API_DIR) & \
	  for i in 1 2 3 4 5 6 7 8 9 10; do \
	    curl -sf http://127.0.0.1:$(PORT_API)/api/v1/health >/dev/null && break; \
	    sleep 1; \
	  done; \
	  curl -sf -X POST http://127.0.0.1:$(PORT_API)/api/v1/projects/demo >/dev/null \
	    && echo "Demo estate loaded." \
	    || { echo "The API did not come up. Run 'make dev-api' to see why."; exit 1; }; \
	  echo "Open http://127.0.0.1:$(PORT_WEB) once the web app is up."; \
	  cd $(WEB_DIR) && NEXT_PUBLIC_API_URL=$(API_URL) npm run dev -- --port $(PORT_WEB)

demo-reset: ## Delete the demo project so the next load re-parses it
	@curl -sf -X DELETE http://127.0.0.1:$(PORT_API)/api/v1/projects/demo-novacart >/dev/null \
	  && echo "Demo project removed." \
	  || echo "Nothing to remove (is the API running?)"

# ----------------------------------------------------------------------------- build

build: ## Production build of the web app
	@cd $(WEB_DIR) && npm run build

# ------------------------------------------------------------------------------ test

test: test-api test-web ## Run every test suite

test-api: ## Backend unit + integration tests
	@$(PY) -m pytest tests -q

test-web: typecheck ## Web app type check and lint
	@cd $(WEB_DIR) && npm run lint

e2e: ## Playwright browser tests (needs both servers running)
	@npx playwright test

check: lint typecheck test-api ## Everything CI would run, except the browser tests

# ----------------------------------------------------------------------------- lint

lint: ## Lint Python and TypeScript
	@$(RUFF) check .
	@cd $(WEB_DIR) && npm run lint

format: ## Auto-fix what can be auto-fixed
	@$(RUFF) check --fix .
	@$(RUFF) format .

typecheck: ## TypeScript type check
	@cd $(WEB_DIR) && npx tsc --noEmit

# ----------------------------------------------------------------------------- misc

doctor: ## Report what is installed and what is optional-but-missing
	@echo "Python:  $$($(PY) --version 2>&1)"
	@echo "Node:    $$(node --version 2>/dev/null || echo 'not installed')"
	@echo "Ollama:  $$(command -v ollama >/dev/null && ollama list 2>/dev/null | tail -n +2 | wc -l | xargs echo 'models installed:' || echo 'not installed (optional)')"
	@$(PY) -c "from api_galaxy.exports import EXPORT_FORMATS; \
	  [print(f\"  {'ok ' if f.available else 'NO '} {f.id:11} {f.unavailable_reason}\") for f in EXPORT_FORMATS]" \
	  2>/dev/null || echo "  (backend not installed yet — run 'make setup')"

clean: ## Remove build artefacts and caches (keeps your projects)
	@rm -rf $(WEB_DIR)/.next $(WEB_DIR)/out .pytest_cache .ruff_cache .mypy_cache
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned."
