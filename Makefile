.PHONY: help setup install install-dev test test-unit test-integration test-e2e test-cov lint format typecheck security check run gui tui health api start-api stop-api restart-api status-api logs-api worker start-worker stop-worker restart-worker status-worker logs-worker stop-all restart-all build standalone standalone-force build-desktop build-desktop-force sign verify cert-generate full-build full-build-desktop install-all docker-build docker-run docker-down docker-logs start stop restart update upgrade status logs postgres-setup postgres-status clean

VENV_DIR ?= .venv
PYTHON ?= $(shell if [ -f "$(VENV_DIR)/bin/python" ]; then echo "$(VENV_DIR)/bin/python"; elif [ -f "$(VENV_DIR)/Scripts/python.exe" ]; then echo "$(VENV_DIR)/Scripts/python.exe"; elif [ -n "$$VIRTUAL_ENV" ]; then echo "$$VIRTUAL_ENV/bin/python"; else echo "python3"; fi)
DIST_DIR ?= dist
CERT_DIR ?= certs
PFX_PATH ?= $(CERT_DIR)/zcoder-codesign.pfx
WEB_VENV := .web-venv
WEB_PY := $(WEB_VENV)/bin/python
WEB_UVICORN := $(WEB_VENV)/bin/uvicorn
PID_FILE := .web.pid
LOG_FILE := logs/web.log
API_PID_FILE := .api.pid
API_LOG_FILE := logs/api.log
WORKER_PID_FILE := .worker.pid
WORKER_LOG_FILE := logs/worker.log
HOST ?= 127.0.0.1
PORT ?= 8420
API_HOST ?= 127.0.0.1
API_PORT ?= 8088
WORKER_ARGS ?=

help:
	@echo "================================================================================"
	@echo "                        ZCoder Enterprise CLI — Makefile Help                   "
	@echo "================================================================================"
	@echo "Environment & Installation:"
	@echo "  make setup              Install environment via scripts/setup.sh or install.py"
	@echo "  make install            Install editable package (base)"
	@echo "  make install-dev        Install editable package with dev dependencies"
	@echo "  make install-all        Install package with all, dev, and postgres extras"
	@echo ""
	@echo "Testing & Quality Gates:"
	@echo "  make test               Run test suite with pytest"
	@echo "  make test-unit          Run unit tests only"
	@echo "  make test-integration   Run postgres-backed integration tests"
	@echo "  make test-e2e           Run end-to-end tests"
	@echo "  make test-cov           Run tests with coverage and missing line reports"
	@echo "  make lint               Run ruff lint check across codebase"
	@echo "  make format             Run black code formatter across codebase"
	@echo "  make typecheck          Run mypy static type analysis"
	@echo "  make security           Run bandit security vulnerability scan"
	@echo "  make check              Run full quality gate (lint + typecheck + security + test-cov)"
	@echo ""
	@echo "Build & Code Signing:"
	@echo "  make standalone         Build platform standalone executable (zcoder or .exe)"
	@echo "  make standalone-force   Force rebuild standalone executable"
	@echo "  make build-desktop      Build full-featured Native Desktop GUI application (zcoder-desktop)"
	@echo "  make cert-generate      Generate Authenticode self-signed certificate into certs/"
	@echo "  Set ZCODER_PFX_PASSWORD in environment before cert-generate/sign; no default is used."
	@echo "  make sign               Sign Windows binaries in dist/ with Authenticode & RFC3161"
	@echo "  make verify             Verify digital signatures in dist/"
	@echo "  make full-build         Complete pipeline: check -> build standalone -> sign"
	@echo "  make full-build-desktop Complete pipeline: check -> build desktop GUI -> sign"
	@echo ""
	@echo "Execution & Runtime:"
	@echo "  make run                Launch ZCoder CLI interactive turn"
	@echo "  make gui                Launch Native Desktop GUI application (Full-feature window)"
	@echo "  make tui                Launch ZCoder Textual TUI interface"
	@echo "  make health             Run enterprise health check"
	@echo "  make api                Start ZCoder REST/API server (foreground)"
	@echo "  make start-api          Start ZCoder REST/API server (background daemon)"
	@echo "  make stop-api           Stop background ZCoder REST/API server"
	@echo "  make restart-api        Restart background ZCoder REST/API server"
	@echo "  make status-api         Check status of background REST/API server"
	@echo "  make logs-api           Tail REST/API server log file"
	@echo "  make worker             Start background queue worker (foreground)"
	@echo "  make start-worker       Start background queue worker (background daemon)"
	@echo "  make stop-worker        Stop background queue worker"
	@echo "  make restart-worker     Restart background queue worker"
	@echo "  make status-worker      Check status of background queue worker"
	@echo "  make logs-worker       Tail background queue worker log file"
	@echo "  make stop-all           Stop all background services (api + worker + web)"
	@echo "  make restart-all        Restart all background services (api + worker + web)"
	@echo ""
	@echo "Web Console:"
	@echo "  make build              Prepare web console environment (.web-venv)"
	@echo "  make start              Start background web console server"
	@echo "  make stop               Stop background web console server"
	@echo "  make restart            Restart web console server"
	@echo "  make status             Display web console status"
	@echo "  make logs               Tail web console log file"
	@echo ""
	@echo "Docker & Database:"
	@echo "  make docker-build       Build ZCoder image (zcoder:latest)"
	@echo "  make docker-run         Run ZCoder with local GGUF inference (ARGS='-p "..."')"
	@echo "  make docker-logs        Follow llama.cpp model-server logs"
	@echo "  make docker-down        Stop local inference and remove Compose resources"
	@echo "  make postgres-setup     Initialize and migrate local PostgreSQL database"
	@echo "  make postgres-status    Inspect local PostgreSQL container status"
	@echo ""
	@echo "Maintenance:"
	@echo "  make update             Update editable installation"
	@echo "  make upgrade            Update and verify runtime version & health"
	@echo "  make clean              Remove build artifacts, caches, and temp directories"
	@echo "================================================================================"

setup:
	@if [ "$$(uname -s)" = "Linux" ] || [ "$$(uname -s)" = "Darwin" ]; then \
		bash scripts/setup.sh; \
	else \
		python scripts/install.py setup; \
	fi

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e '.[dev]'

install-all:
	$(PYTHON) -m pip install -e '.[all,dev,postgres]'

test:
	$(PYTHON) -m pytest

test-unit:
	$(PYTHON) -m pytest tests/unit

test-integration:
	$(PYTHON) scripts/local_postgres.py run -- $(PYTHON) -m pytest tests/integration

test-e2e:
	$(PYTHON) -m pytest tests/e2e

test-cov:
	$(PYTHON) -m pytest --cov --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m black .

typecheck:
	$(PYTHON) -m mypy src/zcoder webapp --ignore-missing-imports

security:
	$(PYTHON) -m bandit -r src/zcoder webapp scripts -ll

check: lint typecheck security test-cov

run:
	$(PYTHON) main.py

gui:
	$(PYTHON) main.py --gui

tui:
	$(PYTHON) main.py --tui

health:
	$(PYTHON) main.py --health-check

api:
	HOST=$(API_HOST) PORT=$(API_PORT) $(PYTHON) scripts/local_postgres.py run -- $(PYTHON) -m zcoder.api.server

start-api:
	@if [ -f $(API_PID_FILE) ] && kill -0 $$(cat $(API_PID_FILE)) 2>/dev/null; then echo "API already running: $$(cat $(API_PID_FILE))"; exit 1; fi
	@mkdir -p logs
	@setsid nohup sh -c 'HOST=$(API_HOST) PORT=$(API_PORT) $(PYTHON) scripts/local_postgres.py run -- $(PYTHON) -m zcoder.api.server' < /dev/null > $(API_LOG_FILE) 2>&1 & echo $$! > $(API_PID_FILE)
	@sleep 1
	@kill -0 $$(cat $(API_PID_FILE)) 2>/dev/null || { echo "API server startup failed; see $(API_LOG_FILE)"; rm -f $(API_PID_FILE); exit 1; }
	@echo "API server started: http://$(API_HOST):$(API_PORT) (PID: $$(cat $(API_PID_FILE)))"

stop-api:
	@if [ ! -f $(API_PID_FILE) ]; then echo "API server not running"; exit 0; fi
	@PID=$$(cat $(API_PID_FILE)); if kill -0 $$PID 2>/dev/null; then kill $$PID; fi
	@rm -f $(API_PID_FILE)
	@echo "API server stopped"

restart-api: stop-api start-api

status-api:
	@if [ -f $(API_PID_FILE) ] && kill -0 $$(cat $(API_PID_FILE)) 2>/dev/null; then echo "API server running (PID: $$(cat $(API_PID_FILE)))"; else echo "API server not running"; fi

logs-api:
	@tail -f $(API_LOG_FILE)

worker:
	$(PYTHON) scripts/local_postgres.py run -- $(PYTHON) -m zcoder.worker.process $(WORKER_ARGS)

start-worker:
	@if [ -f $(WORKER_PID_FILE) ] && kill -0 $$(cat $(WORKER_PID_FILE)) 2>/dev/null; then echo "Worker already running: $$(cat $(WORKER_PID_FILE))"; exit 1; fi
	@mkdir -p logs
	@setsid nohup $(PYTHON) scripts/local_postgres.py run -- $(PYTHON) -m zcoder.worker.process $(WORKER_ARGS) < /dev/null > $(WORKER_LOG_FILE) 2>&1 & echo $$! > $(WORKER_PID_FILE)
	@sleep 1
	@kill -0 $$(cat $(WORKER_PID_FILE)) 2>/dev/null || { echo "Worker startup failed; see $(WORKER_LOG_FILE)"; rm -f $(WORKER_PID_FILE); exit 1; }
	@echo "Worker started (PID: $$(cat $(WORKER_PID_FILE)))"

stop-worker:
	@if [ ! -f $(WORKER_PID_FILE) ]; then echo "Worker not running"; exit 0; fi
	@PID=$$(cat $(WORKER_PID_FILE)); if kill -0 $$PID 2>/dev/null; then kill $$PID; fi
	@rm -f $(WORKER_PID_FILE)
	@echo "Worker stopped"

restart-worker: stop-worker start-worker

status-worker:
	@if [ -f $(WORKER_PID_FILE) ] && kill -0 $$(cat $(WORKER_PID_FILE)) 2>/dev/null; then echo "Worker running (PID: $$(cat $(WORKER_PID_FILE)))"; else echo "Worker not running"; fi

logs-worker:
	@tail -f $(WORKER_LOG_FILE)

stop-all: stop-api stop-worker stop
	@echo "All services stopped"

restart-all: restart-api restart-worker restart
	@echo "All services restarted"

# Preserve the historical `make build` behavior for the web console.
build:
	@test -d $(WEB_VENV) || $(PYTHON) -m venv $(WEB_VENV)
	$(WEB_PY) -m pip install --upgrade pip
	$(WEB_PY) -m pip install -e '.[web]'
	@mkdir -p logs
	@echo "Web environment ready: $(WEB_VENV)"

standalone:
	@if [ "$$(uname -s)" = "Linux" ] || [ "$$(uname -s)" = "Darwin" ]; then \
		bash scripts/build.sh; \
	else \
		python scripts/install.py build; \
	fi

standalone-force:
	@if [ "$$(uname -s)" = "Linux" ] || [ "$$(uname -s)" = "Darwin" ]; then \
		bash scripts/build.sh --force; \
	else \
		python scripts/install.py build --force; \
	fi

build-desktop:
	$(PYTHON) scripts/install.py build --desktop

build-desktop-force:
	$(PYTHON) scripts/install.py build --desktop --force

cert-generate:
	@echo "==> Generating Authenticode Code-Signing Certificate..."
	@powershell.exe -ExecutionPolicy Bypass -File scripts/make_cert.ps1 -OutDir $(CERT_DIR) -ExportPfx -InstallToTrustStore 2>/dev/null || \
	powershell -ExecutionPolicy Bypass -File scripts/make_cert.ps1 -OutDir $(CERT_DIR) -ExportPfx -InstallToTrustStore 2>/dev/null || \
	pwsh -ExecutionPolicy Bypass -File scripts/make_cert.ps1 -OutDir $(CERT_DIR) -ExportPfx -InstallToTrustStore 2>/dev/null || \
	echo "[NOTE] Code-signing certificate generation is only supported on Windows PowerShell / pwsh."

sign:
	@echo "==> Authenticode Code-Signing & RFC3161 Timestamping..."
	@powershell.exe -ExecutionPolicy Bypass -File scripts/sign_exe.ps1 -SearchPath $(DIST_DIR) -Pfx $(PFX_PATH) 2>/dev/null || \
	powershell -ExecutionPolicy Bypass -File scripts/sign_exe.ps1 -SearchPath $(DIST_DIR) -Pfx $(PFX_PATH) 2>/dev/null || \
	pwsh -ExecutionPolicy Bypass -File scripts/sign_exe.ps1 -SearchPath $(DIST_DIR) -Pfx $(PFX_PATH) 2>/dev/null || \
	echo "[NOTE] Authenticode signing applies to Windows binaries (.exe, .dll) via PowerShell."

verify:
	@echo "==> Verifying Digital Signatures..."
	@powershell.exe -ExecutionPolicy Bypass -File scripts/sign_exe.ps1 -SearchPath $(DIST_DIR) -VerifyOnly 2>/dev/null || \
	powershell -ExecutionPolicy Bypass -File scripts/sign_exe.ps1 -SearchPath $(DIST_DIR) -VerifyOnly 2>/dev/null || \
	pwsh -ExecutionPolicy Bypass -File scripts/sign_exe.ps1 -SearchPath $(DIST_DIR) -VerifyOnly 2>/dev/null || \
	echo "[NOTE] Digital signature verification applies to Windows binaries (.exe) via PowerShell."

full-build: check standalone-force
	@echo "==> Standalone build completed successfully."
	@if [ -f "$(DIST_DIR)/zcoder.exe" ]; then \
		$(MAKE) sign; \
	else \
		echo "Built platform executable: $$(ls $(DIST_DIR)/zcoder* 2>/dev/null)"; \
	fi

full-build-desktop: check build-desktop-force
	@echo "==> Desktop GUI standalone build completed successfully."
	@if [ -f "$(DIST_DIR)/zcoder-desktop.exe" ]; then \
		$(MAKE) sign; \
	else \
		echo "Built platform executable: $$(ls $(DIST_DIR)/zcoder-desktop* 2>/dev/null)"; \
	fi

start:
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then echo "already running: $$(cat $(PID_FILE))"; exit 1; fi
	@test -x $(WEB_UVICORN) || { echo "run 'make build' first"; exit 1; }
	@mkdir -p logs
	@setsid nohup $(WEB_UVICORN) webapp.backend.server:app --app-dir . --host $(HOST) --port $(PORT) < /dev/null > $(LOG_FILE) 2>&1 & echo $$! > $(PID_FILE)
	@sleep 1
	@kill -0 $$(cat $(PID_FILE)) 2>/dev/null || { echo "web startup failed; see $(LOG_FILE)"; rm -f $(PID_FILE); exit 1; }
	@echo "started: http://$(HOST):$(PORT)"

stop:
	@if [ ! -f $(PID_FILE) ]; then echo "not running"; exit 0; fi
	@PID=$$(cat $(PID_FILE)); if kill -0 $$PID 2>/dev/null; then kill $$PID; fi
	@rm -f $(PID_FILE)

restart: stop start

update:
	$(PYTHON) -m pip install --upgrade -e .

upgrade: update
	$(PYTHON) main.py --version
	$(PYTHON) main.py --health-check || true

status:
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then echo "running: $$(cat $(PID_FILE))"; else echo "not running"; fi

logs:
	@tail -f $(LOG_FILE)

postgres-setup:
	$(PYTHON) scripts/local_postgres.py setup

postgres-status:
	$(PYTHON) scripts/local_postgres.py status

docker-build:
	docker compose build zcoder

docker-run:
	docker compose run --build --rm zcoder $(ARGS)

docker-down:
	docker compose down

docker-logs:
	docker compose logs --tail=100 -f llama-server

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov build dist
