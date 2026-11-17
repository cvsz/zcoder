.PHONY: help \
	help-install help-test help-build help-run help-api help-worker help-service help-web help-docker help-opencode help-maintenance \
	setup install install-dev install-all \
	test test-unit test-integration test-e2e test-cov lint format typecheck security check \
	standalone standalone-force build-desktop build-desktop-force build-install cert-generate sign verify full-build full-build-desktop \
	run gui tui health \
	api start-api stop-api restart-api status-api logs-api \
	worker start-worker stop-worker restart-worker status-worker logs-worker \
	stop-all restart-all start-all status-all \
	build start stop restart update upgrade status logs \
	postgres-setup postgres-status \
	opencode opencode-prompt opencode-free-prompt opencode-bg opencode-free-bg opencode-models opencode-free-models opencode-nvidia-models opencode-kilo-models \
	docker-build docker-up docker-run docker-down docker-logs \
	clean

# ──────────────────────────────────────────────────────────────────────────────
# Variables / Configuration
# ──────────────────────────────────────────────────────────────────────────────
VENV_DIR      ?= .venv
PYTHON        ?= $(shell if [ -f "$(VENV_DIR)/bin/python" ]; then echo "$(VENV_DIR)/bin/python"; elif [ -f "$(VENV_DIR)/Scripts/python.exe" ]; then echo "$(VENV_DIR)/Scripts/python.exe"; elif [ -n "$$VIRTUAL_ENV" ]; then echo "$$VIRTUAL_ENV/bin/python"; else echo "python3"; fi)
DIST_DIR      ?= dist
CERT_DIR      ?= certs
PFX_PATH      ?= $(CERT_DIR)/zcoder-codesign.pfx
WEB_VENV      := .web-venv
WEB_PY        := $(WEB_VENV)/bin/python
WEB_UVICORN   := $(WEB_VENV)/bin/uvicorn
PID_FILE      := .web.pid
LOG_FILE      := logs/web.log
API_PID_FILE  := .api.pid
API_LOG_FILE  := logs/api.log
WORKER_PID_FILE := .worker.pid
WORKER_LOG_FILE := logs/worker.log
HOST          ?= 127.0.0.1
PORT          ?= 8420
API_HOST      ?= 127.0.0.1
API_PORT      ?= 8088
WORKER_ARGS   ?=
OPENCODE_BIN  ?= $(shell which opencode 2>/dev/null || echo "$$HOME/.opencode/bin/opencode")
OPENCODE_MODEL      ?= nvidia/nvidia/nemotron-3.5-super-vl-120b-a12b
OPENCODE_FREE_MODEL ?= opencode/nemotron-3.5-lightning-free
PROMPT        ?=

# ──────────────────────────────────────────────────────────────────────────────
# Help System (Category-based)
# ──────────────────────────────────────────────────────────────────────────────

# Main help - shows categories
help:
	@echo "================================================================================"
	@echo "                        ZCoder Enterprise CLI — Makefile Help                   "
	@echo "================================================================================"
	@echo ""
	@echo "Usage: make <target>                    # Run a target"
	@echo "       make help-<category>             # Show detailed help for a category"
	@echo ""
	@echo "Categories:"
	@echo "  \033[1;36minstall\033[0m        Environment & Installation        (make help-install)"
	@echo "  \033[1;36mtest\033[0m           Testing & Quality Gates             (make help-test)"
	@echo "  \033[1;36mbuild\033[0m          Build & Code Signing                (make help-build)"
	@echo "  \033[1;36mrun\033[0m            Execution & Runtime (CLI/GUI/TUI)   (make help-run)"
	@echo "  \033[1;36mapi\033[0m            API Server (REST/API)               (make help-api)"
	@echo "  \033[1;36mworker\033[0m         Background Queue Worker             (make help-worker)"
	@echo "  \033[1;36mservice\033[0m        Service Orchestration (All Services) (make help-service)"
	@echo "  \033[1;36mweb\033[0m            Web Console                         (make help-web)"
	@echo "  \033[1;36mdocker\033[0m         Docker & Database                   (make help-docker)"
	@echo "  \033[1;36mopencode\033[0m       OpenCode Integration                (make help-opencode)"
	@echo "  \033[1;36mmaintenance\033[0m    Maintenance & Cleanup               (make help-maintenance)"
	@echo ""
	@echo "Quick Reference (common targets):"
	@echo "  make setup              # Full environment setup"
	@echo "  make install-dev        # Install with dev dependencies"
	@echo "  make check              # Full quality gate (lint + typecheck + security + test-cov)"
	@echo "  make run                # Launch ZCoder CLI interactive"
	@echo "  make gui                # Launch Native Desktop GUI"
	@echo "  make start-all          # Start ALL services (docker + web + api + worker)"
	@echo "  make status-all         # Show status of ALL services"
	@echo "  make opencode           # Run OpenCode CLI"
	@echo "  make clean              # Remove build artifacts and caches"
	@echo "================================================================================"

# ──────────────────────────────────────────────────────────────────────────────
# Category: install
# ──────────────────────────────────────────────────────────────────────────────
help-install:
	@echo "================================================================================"
	@echo "  Category: \033[1;36mEnvironment & Installation\033[0m"
	@echo "================================================================================"
	@echo ""
	@echo "  \033[1;33msetup\033[0m              Install environment via scripts/setup.sh or install.py"
	@echo "                        (detects OS: Linux/macOS -> bash, Windows -> python)"
	@echo ""
	@echo "  \033[1;33minstall\033[0m            Install editable package (base dependencies only)"
	@echo "                        Usage: make install"
	@echo ""
	@echo "  \033[1;33minstall-dev\033[0m        Install editable package with dev dependencies"
	@echo "                        Usage: make install-dev"
	@echo ""
	@echo "  \033[1;33minstall-all\033[0m        Install package with all extras: [all,dev,postgres]"
	@echo "                        Usage: make install-all"
	@echo ""
	@echo "Examples:"
	@echo "  make setup              # First-time setup"
	@echo "  make install-dev        # Daily development install"
	@echo "================================================================================"

# ──────────────────────────────────────────────────────────────────────────────
# Category: test
# ──────────────────────────────────────────────────────────────────────────────
help-test:
	@echo "================================================================================"
	@echo "  Category: \033[1;36mTesting & Quality Gates\033[0m"
	@echo "================================================================================"
	@echo ""
	@echo "  \033[1;33mtest\033[0m               Run full test suite with pytest"
	@echo "                        Usage: make test"
	@echo ""
	@echo "  \033[1;33mtest-unit\033[0m          Run unit tests only (fast, no external deps)"
	@echo "                        Usage: make test-unit"
	@echo ""
	@echo "  \033[1;33mtest-integration\033[0m   Run postgres-backed integration tests"
	@echo "                        Usage: make test-integration"
	@echo ""
	@echo "  \033[1;33mtest-e2e\033[0m           Run end-to-end tests"
	@echo "                        Usage: make test-e2e"
	@echo ""
	@echo "  \033[1;33mtest-cov\033[0m           Run tests with coverage and missing line reports"
	@echo "                        Usage: make test-cov"
	@echo ""
	@echo "  \033[1;33mlint\033[0m               Run ruff lint check across codebase"
	@echo "                        Usage: make lint"
	@echo ""
	@echo "  \033[1;33mformat\033[0m             Run black code formatter across codebase"
	@echo "                        Usage: make format"
	@echo ""
	@echo "  \033[1;33mtypecheck\033[0m          Run mypy static type analysis"
	@echo "                        Usage: make typecheck"
	@echo ""
	@echo "  \033[1;33msecurity\033[0m           Run bandit security vulnerability scan"
	@echo "                        Usage: make security"
	@echo ""
	@echo "  \033[1;33mcheck\033[0m              Run FULL quality gate: lint + typecheck + security + test-cov"
	@echo "                        Usage: make check"
	@echo ""
	@echo "Examples:"
	@echo "  make check              # CI-quality gate (run before PR)"
	@echo "  make test-unit          # Quick unit test run"
	@echo "  make test-integration   # Integration tests (needs postgres)"
	@echo "================================================================================"

# ──────────────────────────────────────────────────────────────────────────────
# Category: build
# ──────────────────────────────────────────────────────────────────────────────
help-build:
	@echo "================================================================================"
	@echo "  Category: \033[1;36mBuild & Code Signing\033[0m"
	@echo "================================================================================"
	@echo ""
	@echo "  \033[1;33mstandalone\033[0m         Build platform standalone executable (zcoder or .exe)"
	@echo "                        Usage: make standalone"
	@echo ""
	@echo "  \033[1;33mstandalone-force\033[0m   Force rebuild standalone executable (clean first)"
	@echo "                        Usage: make standalone-force"
	@echo ""
	@echo "  \033[1;33mbuild-install\033[0m      Build and install executable to ~/.local/bin/zcoder"
	@echo "                        Usage: make build-install"
	@echo ""
	@echo "  \033[1;33mbuild-desktop\033[0m      Build full-featured Native Desktop GUI (zcoder-desktop)"
	@echo "                        Usage: make build-desktop"
	@echo ""
	@echo "  \033[1;33mbuild-desktop-force\033[0m Force rebuild desktop GUI application"
	@echo "                        Usage: make build-desktop-force"
	@echo ""
	@echo "  \033[1;33mcert-generate\033[0m      Generate Authenticode self-signed certificate into certs/"
	@echo "                        (Windows PowerShell / pwsh only)"
	@echo "                        Usage: make cert-generate"
	@echo ""
	@echo "  \033[1;33msign\033[0m               Sign Windows binaries in dist/ with Authenticode & RFC3161"
	@echo "                        Usage: make sign"
	@echo ""
	@echo "  \033[1;33mverify\033[0m             Verify digital signatures in dist/"
	@echo "                        Usage: make verify"
	@echo ""
	@echo "  \033[1;33mfull-build\033[0m         Complete pipeline: check -> build standalone -> sign"
	@echo "                        Usage: make full-build"
	@echo ""
	@echo "  \033[1;33mfull-build-desktop\033[0m Complete pipeline: check -> build desktop GUI -> sign"
	@echo "                        Usage: make full-build-desktop"
	@echo ""
	@echo "Examples:"
	@echo "  make full-build         # Production CLI build with signing"
	@echo "  make full-build-desktop # Production GUI build with signing"
	@echo "  make build-install      # Build and install to ~/.local/bin"
	@echo "  make cert-generate      # Generate code-signing cert (Windows)"
	@echo "================================================================================"

# ──────────────────────────────────────────────────────────────────────────────
# Category: run
# ──────────────────────────────────────────────────────────────────────────────
help-run:
	@echo "================================================================================"
	@echo "  Category: \033[1;36mExecution & Runtime (CLI / GUI / TUI / Health)\033[0m"
	@echo "================================================================================"
	@echo ""
	@echo "  \033[1;33mrun\033[0m                Launch ZCoder CLI interactive turn"
	@echo "                        Usage: make run"
	@echo ""
	@echo "  \033[1;33mgui\033[0m                Launch Native Desktop GUI application (Full-feature window)"
	@echo "                        Usage: make gui"
	@echo ""
	@echo "  \033[1;33mtui\033[0m                Launch ZCoder Textual TUI interface"
	@echo "                        Usage: make tui"
	@echo ""
	@echo "  \033[1;33mhealth\033[0m             Run enterprise health check"
	@echo "                        Usage: make health"
	@echo ""
	@echo "Examples:"
	@echo "  make run                # Interactive CLI session"
	@echo "  make gui                # Desktop GUI application"
	@echo "  make tui                # Terminal UI (Textual)"
	@echo "  make health             # System health verification"
	@echo "================================================================================"

# ──────────────────────────────────────────────────────────────────────────────
# Category: api
# ──────────────────────────────────────────────────────────────────────────────
help-api:
	@echo "================================================================================"
	@echo "  Category: \033[1;36mAPI Server (REST/API)\033[0m"
	@echo "================================================================================"
	@echo ""
	@echo "  \033[1;33mapi\033[0m                Start ZCoder REST/API server (foreground)"
	@echo "                        Usage: make api"
	@echo ""
	@echo "  \033[1;33mstart-api\033[0m          Start ZCoder REST/API server (background daemon)"
	@echo "                        Usage: make start-api"
	@echo ""
	@echo "  \033[1;33mstop-api\033[0m           Stop background ZCoder REST/API server"
	@echo "                        Usage: make stop-api"
	@echo ""
	@echo "  \033[1;33mrestart-api\033[0m        Restart background ZCoder REST/API server"
	@echo "                        Usage: make restart-api"
	@echo ""
	@echo "  \033[1;33mstatus-api\033[0m         Check status of background REST/API server"
	@echo "                        Usage: make status-api"
	@echo ""
	@echo "  \033[1;33mlogs-api\033[0m           Tail REST/API server log file"
	@echo "                        Usage: make logs-api"
	@echo ""
	@echo "Environment variables:"
	@echo "  API_HOST=127.0.0.1  API_PORT=8088"
	@echo ""
	@echo "Examples:"
	@echo "  make start-api          # Start API in background"
	@echo "  make status-api         # Check if running"
	@echo "  make logs-api           # Follow logs"
	@echo "  make stop-api           # Stop API server"
	@echo "================================================================================"

# ──────────────────────────────────────────────────────────────────────────────
# Category: worker
# ──────────────────────────────────────────────────────────────────────────────
help-worker:
	@echo "================================================================================"
	@echo "  Category: \033[1;36mBackground Queue Worker\033[0m"
	@echo "================================================================================"
	@echo ""
	@echo "  \033[1;33mworker\033[0m             Start background queue worker (foreground)"
	@echo "                        Usage: make worker"
	@echo ""
	@echo "  \033[1;33mstart-worker\033[0m       Start background queue worker (background daemon)"
	@echo "                        Usage: make start-worker"
	@echo ""
	@echo "  \033[1;33mstop-worker\033[0m        Stop background queue worker"
	@echo "                        Usage: make stop-worker"
	@echo ""
	@echo "  \033[1;33mrestart-worker\033[0m     Restart background queue worker"
	@echo "                        Usage: make restart-worker"
	@echo ""
	@echo "  \033[1;33mstatus-worker\033[0m      Check status of background queue worker"
	@echo "                        Usage: make status-worker"
	@echo ""
	@echo "  \033[1;33mlogs-worker\033[0m        Tail background queue worker log file"
	@echo "                        Usage: make logs-worker"
	@echo ""
	@echo "Environment variables:"
	@echo "  WORKER_ARGS=        Extra arguments for worker process"
	@echo ""
	@echo "Examples:"
	@echo "  make start-worker       # Start worker in background"
	@echo "  make status-worker      # Check worker status"
	@echo "  make logs-worker        # Follow worker logs"
	@echo "================================================================================"

# ──────────────────────────────────────────────────────────────────────────────
# Category: service
# ──────────────────────────────────────────────────────────────────────────────
help-service:
	@echo "================================================================================"
	@echo "  Category: \033[1;36mService Orchestration (All Services)\033[0m"
	@echo "================================================================================"
	@echo ""
	@echo "  \033[1;33mstart-all\033[0m          Start ALL services (docker + web + api + worker)"
	@echo "                        Usage: make start-all"
	@echo ""
	@echo "  \033[1;33mstop-all\033[0m           Stop all background services (api + worker + web)"
	@echo "                        Usage: make stop-all"
	@echo ""
	@echo "  \033[1;33mrestart-all\033[0m        Restart all background services (api + worker + web)"
	@echo "                        Usage: make restart-all"
	@echo ""
	@echo "  \033[1;33mstatus-all\033[0m         Show status of ALL services (docker + web + api + worker)"
	@echo "                        Usage: make status-all"
	@echo ""
	@echo "Examples:"
	@echo "  make start-all          # Start everything for development"
	@echo "  make status-all         # Check all service statuses"
	@echo "  make stop-all           # Stop all background services"
	@echo "================================================================================"

# ──────────────────────────────────────────────────────────────────────────────
# Category: web
# ──────────────────────────────────────────────────────────────────────────────
help-web:
	@echo "================================================================================"
	@echo "  Category: \033[1;36mWeb Console\033[0m"
	@echo "================================================================================"
	@echo ""
	@echo "  \033[1;33mbuild\033[0m              Prepare web console environment (.web-venv)"
	@echo "                        Installs [web] extra dependencies"
	@echo "                        Usage: make build"
	@echo ""
	@echo "  \033[1;33mstart\033[0m              Start background web console server"
	@echo "                        Usage: make start"
	@echo ""
	@echo "  \033[1;33mstop\033[0m               Stop background web console server"
	@echo "                        Usage: make stop"
	@echo ""
	@echo "  \033[1;33mrestart\033[0m            Restart web console server"
	@echo "                        Usage: make restart"
	@echo ""
	@echo "  \033[1;33mstatus\033[0m             Display web console status"
	@echo "                        Usage: make status"
	@echo ""
	@echo "  \033[1;33mlogs\033[0m               Tail web console log file"
	@echo "                        Usage: make logs"
	@echo ""
	@echo "Environment variables:"
	@echo "  HOST=127.0.0.1  PORT=8420"
	@echo ""
	@echo "Examples:"
	@echo "  make build              # Setup web environment (run once)"
	@echo "  make start              # Start web console at http://localhost:8420"
	@echo "  make status             # Check if running"
	@echo "  make logs               # Follow web console logs"
	@echo "================================================================================"

# ──────────────────────────────────────────────────────────────────────────────
# Category: docker
# ──────────────────────────────────────────────────────────────────────────────
help-docker:
	@echo "================================================================================"
	@echo "  Category: \033[1;36mDocker & Database\033[0m"
	@echo "================================================================================"
	@echo ""
	@echo "  \033[1;33mdocker-build\033[0m       Build ZCoder image (zcoder:latest)"
	@echo "                        Usage: make docker-build"
	@echo ""
	@echo "  \033[1;33mdocker-up\033[0m          Start all Docker services (llama.cpp, PostgreSQL, ZCoder)"
	@echo "                        Usage: make docker-up"
	@echo ""
	@echo "  \033[1;33mdocker-run\033[0m         Run ZCoder with local GGUF inference"
	@echo "                        Usage: make docker-run ARGS='-p \"prompt\"'"
	@echo ""
	@echo "  \033[1;33mdocker-down\033[0m        Stop local inference and remove Compose resources"
	@echo "                        Usage: make docker-down"
	@echo ""
	@echo "  \033[1;33mdocker-logs\033[0m        Follow llama.cpp model-server logs"
	@echo "                        Usage: make docker-logs"
	@echo ""
	@echo "  \033[1;33mpostgres-setup\033[0m     Initialize and migrate local PostgreSQL database"
	@echo "                        Usage: make postgres-setup"
	@echo ""
	@echo "  \033[1;33mpostgres-status\033[0m    Inspect local PostgreSQL container status"
	@echo "                        Usage: make postgres-status"
	@echo ""
	@echo "Examples:"
	@echo "  make docker-up          # Start all containers"
	@echo "  make docker-run ARGS='-p \"hello\"'  # Run inference in container"
	@echo "  make postgres-setup     # Initialize database"
	@echo "  make docker-down        # Clean shutdown"
	@echo "================================================================================"

# ──────────────────────────────────────────────────────────────────────────────
# Category: opencode
# ──────────────────────────────────────────────────────────────────────────────
help-opencode:
	@echo "================================================================================"
	@echo "  Category: \033[1;36mOpenCode Integration\033[0m"
	@echo "================================================================================"
	@echo ""
	@echo "  \033[1;33mopencode\033[0m           Run OpenCode CLI (loads .env automatically)"
	@echo "                        Usage: make opencode"
	@echo "                        Usage: make opencode PROMPT=\"prompt\""
	@echo ""
	@echo "  \033[1;33mopencode-prompt\033[0m    Execute prompt via OpenCode (requires PROMPT)"
	@echo "                        Usage: make opencode-prompt PROMPT=\"your prompt\" [OPENCODE_MODEL=\"...\"]"
	@echo ""
	@echo "  \033[1;33mopencode-free-prompt\033[0m Execute prompt using 100% Free Model (requires PROMPT)"
	@echo "                        Usage: make opencode-free-prompt PROMPT=\"your prompt\" [OPENCODE_FREE_MODEL=\"...\"]"
	@echo ""
	@echo "  \033[1;33mopencode-bg\033[0m        Run OpenCode prompt in background (requires PROMPT)"
	@echo "                        Usage: make opencode-bg PROMPT=\"your prompt\" [OPENCODE_MODEL=\"...\"]"
	@echo ""
	@echo "  \033[1;33mopencode-free-bg\033[0m   Run OpenCode free model in background (requires PROMPT)"
	@echo "                        Usage: make opencode-free-bg PROMPT=\"your prompt\" [OPENCODE_FREE_MODEL=\"...\"]"
	@echo ""
	@echo "  \033[1;33mopencode-models\033[0m    List all available OpenCode models"
	@echo "                        Usage: make opencode-models"
	@echo ""
	@echo "  \033[1;33mopencode-free-models\033[0m List all available free models (NVIDIA, OpenCode, Kilo, etc.)"
	@echo "                        Usage: make opencode-free-models"
	@echo ""
	@echo "  \033[1;33mopencode-nvidia-models\033[0m List NVIDIA Nemotron & NIM models"
	@echo "                        Usage: make opencode-nvidia-models"
	@echo ""
	@echo "  \033[1;33mopencode-kilo-models\033[0m List Kilo models & free routers"
	@echo "                        Usage: make opencode-kilo-models"
	@echo ""
	@echo "Environment variables:"
	@echo "  OPENCODE_MODEL=...        Default: nvidia/nvidia/nemotron-3.5-super-vl-120b-a12b"
	@echo "  OPENCODE_FREE_MODEL=...   Default: opencode/nemotron-3.5-lightning-free"
	@echo "  PROMPT=...                Required for prompt targets"
	@echo ""
	@echo "Examples:"
	@echo "  make opencode                           # Interactive OpenCode"
	@echo "  make opencode-prompt PROMPT=\"fix bug\"   # One-shot prompt"
	@echo "  make opencode-free-prompt PROMPT=\"code\" # Free model prompt"
	@echo "  make opencode-bg PROMPT=\"long task\"     # Background execution"
	@echo "  make opencode-models                    # List all models"
	@echo "================================================================================"

# ──────────────────────────────────────────────────────────────────────────────
# Category: maintenance
# ──────────────────────────────────────────────────────────────────────────────
help-maintenance:
	@echo "================================================================================"
	@echo "  Category: \033[1;36mMaintenance & Cleanup\033[0m"
	@echo "================================================================================"
	@echo ""
	@echo "  \033[1;33mupdate\033[0m             Update editable installation (pip install --upgrade -e .)"
	@echo "                        Usage: make update"
	@echo ""
	@echo "  \033[1;33mupgrade\033[0m            Update and verify runtime version & health"
	@echo "                        Runs update, then --version and --health-check"
	@echo "                        Usage: make upgrade"
	@echo ""
	@echo "  \033[1;33mclean\033[0m              Remove build artifacts, caches, and temp directories"
	@echo "                        Removes: __pycache__, .pytest_cache, .mypy_cache,"
	@echo "                        .ruff_cache, .coverage, coverage.xml, htmlcov, build, dist"
	@echo "                        Usage: make clean"
	@echo ""
	@echo "Examples:"
	@echo "  make upgrade            # Update package and verify health"
	@echo "  make clean              # Clean all build artifacts"
	@echo "================================================================================"

# ──────────────────────────────────────────────────────────────────────────────
# Environment & Installation
# ──────────────────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────
# Testing & Quality Gates
# ──────────────────────────────────────────────────────────────────────────────
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
validated: check security-proven
security-proven:
	@echo "Running security verification..."
	@python -m bandit -r src/zcoder -ll
	@echo "Security verification complete"
	@echo ""
validated: check security-proven

# ──────────────────────────────────────────────────────────────────────────────
# Build & Code Signing
# ──────────────────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────
# Install built executable to user's local bin
# ──────────────────────────────────────────────────────────────────────────────
build-install: standalone
	@echo "==> Installing zcoder to ~/.local/bin..."
	@mkdir -p "$$HOME/.local/bin"
	@if [ "$$(uname -s)" = "Linux" ] || [ "$$(uname -s)" = "Darwin" ]; then \
		cp $(DIST_DIR)/zcoder "$$HOME/.local/bin/zcoder"; \
		chmod +x "$$HOME/.local/bin/zcoder"; \
		echo "Installed: $$HOME/.local/bin/zcoder"; \
	else \
		cp $(DIST_DIR)/zcoder.exe "$$HOME/.local/bin/zcoder.exe"; \
		echo "Installed: $$HOME/.local/bin/zcoder.exe"; \
	fi
	@echo "Ensure $$HOME/.local/bin is in your PATH"

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

# ──────────────────────────────────────────────────────────────────────────────
# Execution & Runtime (CLI / GUI / TUI / Health)
# ──────────────────────────────────────────────────────────────────────────────
run:
	$(PYTHON) main.py

gui:
	$(PYTHON) main.py --gui

tui:
	$(PYTHON) main.py --tui

health:
	$(PYTHON) main.py --health-check

# ──────────────────────────────────────────────────────────────────────────────
# API Server (REST/API)
# ──────────────────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────
# Background Queue Worker
# ──────────────────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────
# Service Orchestration (All Services)
# ──────────────────────────────────────────────────────────────────────────────
stop-all: stop-api stop-worker stop
	@echo "All services stopped"

restart-all: restart-api restart-worker restart
	@echo "All services restarted"

start-all:
	@$(MAKE) docker-up || true
	@$(MAKE) start || true
	@$(MAKE) start-api || true
	@$(MAKE) start-worker || true
	@echo "All services started"
	@echo "  Web console: http://$(HOST):$(PORT)"
	@echo "  API server:  http://$(API_HOST):$(API_PORT)"
	@echo "  Docker:      ollama + PostgreSQL + ZCoder container"

status-all:
	@echo "=== ZCoder Service Status ==="
	@echo ""
	@echo "-- Docker containers --"
	@docker compose ps 2>/dev/null || echo "  Docker not available or no containers"
	@echo ""
	@$(MAKE) status
	@$(MAKE) status-api
	@$(MAKE) status-worker
	@echo ""
	@echo "=== End status ==="

# ──────────────────────────────────────────────────────────────────────────────
# Web Console
# ──────────────────────────────────────────────────────────────────────────────
build:
	@test -d $(WEB_VENV) || $(PYTHON) -m venv $(WEB_VENV)
	$(WEB_PY) -m pip install --upgrade pip
	$(WEB_PY) -m pip install -e '.[web]'
	@mkdir -p logs
	@echo "Web environment ready: $(WEB_VENV)"

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

status:
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then echo "running: $$(cat $(PID_FILE))"; else echo "not running"; fi

logs:
	@tail -f $(LOG_FILE)

# ──────────────────────────────────────────────────────────────────────────────
# Docker & Database
# ──────────────────────────────────────────────────────────────────────────────
docker-build:
	docker compose build zcoder

docker-up:
	docker compose --env-file .env up -d

docker-run:
	docker compose run --build --rm zcoder $(ARGS)

docker-down:
	docker compose down

docker-logs:
	docker compose logs --tail=100 -f ollama

postgres-setup:
	$(PYTHON) scripts/local_postgres.py setup

postgres-status:
	$(PYTHON) scripts/local_postgres.py status

# ──────────────────────────────────────────────────────────────────────────────
# OpenCode Integration
# ──────────────────────────────────────────────────────────────────────────────
opencode:
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	if [ -n "$(PROMPT)" ]; then \
		$(OPENCODE_BIN) run -m "$(OPENCODE_MODEL)" $(PROMPT); \
	else \
		$(OPENCODE_BIN); \
	fi

opencode-prompt:
	@if [ -z "$(PROMPT)" ]; then \
		echo "Error: PROMPT is required. Usage: make opencode-prompt PROMPT=\"your prompt\" [OPENCODE_MODEL=\"...\"]" >&2; \
		exit 1; \
	fi; \
	if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	$(OPENCODE_BIN) run -m "$(OPENCODE_MODEL)" $(PROMPT)

opencode-free-prompt:
	@if [ -z "$(PROMPT)" ]; then \
		echo "Error: PROMPT is required. Usage: make opencode-free-prompt PROMPT=\"your prompt\" [OPENCODE_FREE_MODEL=\"...\"]" >&2; \
		exit 1; \
	fi; \
	if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	$(OPENCODE_BIN) run -m "$(OPENCODE_FREE_MODEL)" $(PROMPT)

opencode-bg:
	@if [ -z "$(PROMPT)" ]; then \
		echo "Error: PROMPT is required. Usage: make opencode-bg PROMPT=\"your prompt\" [OPENCODE_MODEL=\"...\"]" >&2; \
		exit 1; \
	fi; \
	mkdir -p logs; \
	if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	nohup $(OPENCODE_BIN) run -m "$(OPENCODE_MODEL)" $(PROMPT) > logs/opencode.log 2>&1 & echo $$! > .opencode.pid; \
	echo "Started OpenCode in background (PID: $$(cat .opencode.pid), logs: logs/opencode.log)"

opencode-free-bg:
	@if [ -z "$(PROMPT)" ]; then \
		echo "Error: PROMPT is required. Usage: make opencode-free-bg PROMPT=\"your prompt\" [OPENCODE_FREE_MODEL=\"...\"]" >&2; \
		exit 1; \
	fi; \
	mkdir -p logs; \
	if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	nohup $(OPENCODE_BIN) run -m "$(OPENCODE_FREE_MODEL)" $(PROMPT) > logs/opencode.log 2>&1 & echo $$! > .opencode.pid; \
	echo "Started OpenCode Free Model in background (PID: $$(cat .opencode.pid), logs: logs/opencode.log)"

opencode-models:
	$(OPENCODE_BIN) models

opencode-free-models:
	@echo "================================================================================"
	@echo "                OpenCode Available Free Models (All Providers)                  "
	@echo "================================================================================"
	@$(OPENCODE_BIN) models | grep -E "(:free|-free)" || $(OPENCODE_BIN) models | grep -i "free"

opencode-nvidia-models:
	@echo "================================================================================"
	@echo "                      NVIDIA / Nemotron Models in OpenCode                     "
	@echo "================================================================================"
	@$(OPENCODE_BIN) models | grep -i "nvidia"

opencode-kilo-models:
	@echo "================================================================================"
	@echo "                       Kilo Provider Models in OpenCode                        "
	@echo "================================================================================"
	@$(OPENCODE_BIN) models | grep -i "^kilo/"

# ──────────────────────────────────────────────────────────────────────────────
# Maintenance
# ──────────────────────────────────────────────────────────────────────────────
update:
	$(PYTHON) -m pip install --upgrade -e .

upgrade: update
	$(PYTHON) main.py --version
	$(PYTHON) main.py --health-check || true

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov build dist