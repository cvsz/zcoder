.PHONY: install install-dev test test-cov lint format typecheck security check run tui docker-build docker-run health clean \
        build start stop restart update upgrade status logs

# ── Web console (webapp/) ───────────────────────────────────────────────
# `build`/`start`/`stop`/`restart`/`update`/`upgrade` all target the
# FastAPI+static web console in webapp/ (backend/server.py + frontend/).
# They never touch the plain CLI (`make run` still runs `python main.py`
# directly, unaffected). All state lives in-repo so these are safe to run
# from a fresh clone with no other setup:
#   .web-venv/            — dedicated virtualenv (kept separate from any
#                            venv you use for CLI development, so upgrading
#                            the web console's deps can never break the CLI)
#   logs/web.log           — server stdout/stderr
#   .web.pid               — pid of the running uvicorn process, if any
VENV        := .web-venv
VENV_PY     := $(VENV)/bin/python
VENV_PIP    := $(VENV)/bin/pip
VENV_UVICORN:= $(VENV)/bin/uvicorn
PID_FILE    := .web.pid
LOG_FILE    := logs/web.log
HOST        ?= 0.0.0.0
PORT        ?= 8420

# Build: create the venv (idempotent) and install/refresh every dependency
# the web console needs — the CLI core's requirements.txt (Coder/etc. import
# straight into the backend, see webapp/backend/server.py) plus
# webapp/requirements-web.txt (fastapi/uvicorn). Nothing to compile for the
# frontend -- it's plain HTML/CSS/JS served as static files, no bundler.
build:
	@test -d $(VENV) || python3 -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip --disable-pip-version-check -q
	$(VENV_PIP) install -q -r requirements.txt -r webapp/requirements-web.txt
	@mkdir -p logs
	@echo "✅ build complete — venv at $(VENV)/"

# Start: refuse to double-start if a live process is already using
# PID_FILE, otherwise launch uvicorn detached (nohup) and record its pid.
start:
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "⚠️  already running (pid $$(cat $(PID_FILE))) — use 'make restart'"; \
		exit 1; \
	fi
	@test -x $(VENV_UVICORN) || { echo "❌ not built yet — run 'make build' first"; exit 1; }
	@mkdir -p logs
	@setsid nohup $(VENV_UVICORN) webapp.backend.server:app --app-dir . \
		--host $(HOST) --port $(PORT) < /dev/null > $(LOG_FILE) 2>&1 & echo $$! > $(PID_FILE)
	@sleep 1
	@if kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "🚀 started (pid $$(cat $(PID_FILE))) — http://$(HOST):$(PORT)  (logs: $(LOG_FILE))"; \
	else \
		echo "❌ failed to start — see $(LOG_FILE)"; rm -f $(PID_FILE); exit 1; \
	fi

# Stop: graceful SIGTERM, falling back to SIGKILL if it won't quit.
stop:
	@if [ ! -f $(PID_FILE) ]; then echo "ℹ️  not running (no $(PID_FILE))"; exit 0; fi
	@PID=$$(cat $(PID_FILE)); \
	if kill -0 $$PID 2>/dev/null; then \
		kill $$PID 2>/dev/null; \
		for i in 1 2 3 4 5; do kill -0 $$PID 2>/dev/null || break; sleep 1; done; \
		kill -0 $$PID 2>/dev/null && kill -9 $$PID 2>/dev/null || true; \
		echo "🛑 stopped (pid $$PID)"; \
	else \
		echo "ℹ️  stale pid file (process $$PID not running)"; \
	fi
	@rm -f $(PID_FILE)

restart: stop start

# Update: refresh dependencies to their latest allowed versions (and pull
# the latest source if this checkout is a git repo). Does not restart the
# server automatically — run `make restart` after if one is running.
update:
	@if [ -d .git ]; then echo "📥 git pull…"; git pull; fi
	@test -d $(VENV) || python3 -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip --disable-pip-version-check -q
	$(VENV_PIP) install -q --upgrade -r requirements.txt -r webapp/requirements-web.txt
	@echo "✅ dependencies updated"

# Upgrade: update()'s superset — also verifies the result, and restarts a
# currently-running server so the upgrade takes effect immediately instead
# of silently running stale code until someone remembers to restart it.
upgrade: update
	@echo "🔎 version: $$($(VENV_PY) main.py --version 2>/dev/null || echo unknown)"
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "🔁 restarting running server to pick up the upgrade…"; \
		$(MAKE) restart; \
	else \
		echo "ℹ️  server wasn't running — 'make start' whenever you're ready"; \
	fi
	@$(VENV_PY) main.py --health-check || true

# Convenience (not part of the core lifecycle, but cheap and useful
# alongside it): current status, and a tail of the live log.
status:
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "🟢 running (pid $$(cat $(PID_FILE))) — http://$(HOST):$(PORT)"; \
	else \
		echo "🔴 not running"; \
	fi

logs:
	@tail -f $(LOG_FILE)

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

test:
	pytest

test-cov:
	pytest --cov --cov-report=term-missing

lint:
	ruff check .

format:
	black .

typecheck:
	mypy . --ignore-missing-imports

security:
	bandit -r . -x ./tests

check: lint typecheck security test-cov

run:
	python main.py

tui:
	python main.py --tui

health:
	python main.py --health-check

docker-build:
	docker build -t zcoder:latest .

docker-run:
	docker run --rm -e ANTHROPIC_API_KEY=$${ANTHROPIC_API_KEY} zcoder:latest

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml dist build
