.PHONY: install install-dev test test-unit test-integration test-e2e test-cov lint format typecheck security check run tui health build standalone docker-build docker-run start stop restart update upgrade status logs clean

PYTHON ?= python3
WEB_VENV := .web-venv
WEB_PY := $(WEB_VENV)/bin/python
WEB_UVICORN := $(WEB_VENV)/bin/uvicorn
PID_FILE := .web.pid
LOG_FILE := logs/web.log
HOST ?= 0.0.0.0
PORT ?= 8420

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e '.[dev]'

test:
	$(PYTHON) -m pytest

test-unit:
	$(PYTHON) -m pytest tests/unit

test-integration:
	$(PYTHON) -m pytest tests/integration

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

tui:
	$(PYTHON) main.py --tui

health:
	$(PYTHON) main.py --health-check

# Preserve the historical `make build` behavior for the web console.
build:
	@test -d $(WEB_VENV) || $(PYTHON) -m venv $(WEB_VENV)
	$(WEB_PY) -m pip install --upgrade pip
	$(WEB_PY) -m pip install -e '.[web]'
	@mkdir -p logs
	@echo "Web environment ready: $(WEB_VENV)"

standalone:
	./scripts/build.sh

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

docker-build:
	docker build -t zcoder:latest .

docker-run:
	docker run --rm -e ANTHROPIC_API_KEY=$${ANTHROPIC_API_KEY} zcoder:latest

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov build dist
