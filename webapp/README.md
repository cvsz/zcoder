# zcoder web console

A browser UI for the ZCoder CLI. It does not replace the CLI or
duplicate its logic — `webapp/backend/server.py` imports and calls the
same `Coder` class, `personalities.py`, `skills.py`, `config.py`, and
`health.py` that `main.py` already uses, and just exposes them over HTTP.

```
webapp/
├── backend/
│   └── server.py       # FastAPI app — thin adapter over the CLI core
├── frontend/
│   ├── index.html       # terminal-styled chat UI (no build step needed)
│   ├── style.css
│   └── app.js
└── requirements-web.txt # fastapi + uvicorn, additive to ../requirements.txt
```

## Quick start

From the project root:

```bash
make build      # create .web-venv/ and install requirements.txt + webapp/requirements-web.txt
export ANTHROPIC_API_KEY=sk-ant-...   # or paste it into the sidebar once running
make start      # launch in the background, http://localhost:8420
make status     # check whether it's up
make logs       # tail logs/web.log
make stop
make restart
make update     # refresh dependencies (and git pull, if this is a git checkout)
make upgrade    # update + restart a running server + health-check
```

Override the local port with `make start PORT=9000`. The default bind address
is `127.0.0.1`, so the unauthenticated development console is not exposed on
all network interfaces. Use an authenticated access layer before making the
console available outside the local machine. The server also allows only local
Host headers and disables cross-origin browser access by default.

For a separately hosted local development frontend, configure an explicit
`ZCODER_WEB_CORS_ORIGINS` allowlist (for example,
`http://localhost:5173`). Do not use wildcard origins or expose the backend
directly to the public internet.

## Without the Makefile

```bash
pip install -r requirements.txt -r webapp/requirements-web.txt
uvicorn webapp.backend.server:app --app-dir . --host 127.0.0.1 --port 8420
```

## API surface

| Method & path              | Wraps                                   |
|-----------------------------|------------------------------------------|
| `POST /api/chat`            | `coder.Coder.generate()`                 |
| `GET  /api/health`          | `health.run_health_check()`              |
| `GET  /api/models`          | `claude_models.MODEL_CATALOG`            |
| `GET  /api/personalities`   | `personalities.PersonalityManager`       |
| `GET  /api/skills`          | `skills.SkillManager`                    |
| `GET  /api/agents`          | `main.AGENT_SYSTEM_PROMPTS`              |
| `GET/POST /api/config`      | `config.Config`                          |
| `GET/DELETE /api/sessions/:id` | in-memory chat history (per-process)  |
| `GET  /api/version`         | `main.VERSION`                           |

Sessions are held in memory only (same lifetime as the CLI's
`--interactive` REPL) and are cleared on restart — there's no database
here, by design, to keep this a thin layer over the existing core rather
than a second source of truth.

The API key entered in the sidebar is sent once to `POST /api/config` and
stored the same place the CLI already reads it from
(`~/.zcoder-config.json` via `config.Config`) — it is never echoed back
in full to the browser afterward.
