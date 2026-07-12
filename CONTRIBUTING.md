# Contributing

## Setup

```bash
git clone <repo>
cd zcoder
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Before opening a PR

```bash
ruff check .
black --check .
mypy . --ignore-missing-imports   # best-effort; not all modules are fully typed yet
bandit -r . -x ./tests
pytest --cov
```

CI (`.github/workflows/ci.yml`) runs all of the above across Python
3.9–3.12 plus a Docker build smoke test. A PR won't merge if any of these
fail.

## Conventions

- **New API calls that hit the network** should raise `exceptions.py`
  types (`TransientAPIError`, `RateLimitError`, `APIError`, ...), not bare
  `Exception`, so `resilience.retry()` can classify them correctly. Wrap
  the call in `@resilience.retry(...)` rather than hand-rolling a retry
  loop. **Exception:** `claude_admin_api.py` and `claude_compliance_api.py`
  implement their own retry/backoff directly, because Anthropic documents
  a specific retry contract for those endpoint families independently of
  the general API's; reusing `resilience.retry()` there would couple two
  contracts that happen to look similar today but aren't guaranteed to
  stay that way. Don't follow this as a general pattern — it's specific
  to those two modules.
- **New user-supplied paths/names** go through `security.safe_resolve()` /
  `security.validate_name()` before touching the filesystem.
- **New logging** uses `logging_config.get_logger(__name__)`, not bare
  `print()` for anything other than direct CLI output the user asked for.
  Structured fields go in `extra={...}`, not string-interpolated into the
  message (keeps JSON log output queryable).
- **New tests** live under `tests/`, one file per module
  (`tests/test_<module>.py`), and must not make real network calls — mock
  `urllib.request.urlopen` as in `tests/test_coder.py`.
- Every `claude_*.py` module documents which CLI flags it backs in its
  module docstring (existing convention — keep it going).

## Versioning

`CHANGELOG.md` is the source of truth for what shipped in each version;
`docs/*_upgrade_*.md` holds the detailed per-release notes for anything
non-trivial. Bump `VERSION` in `main.py` and `version` in `pyproject.toml`
together.
