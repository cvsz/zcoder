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
make build      # create .web-venv/ and install the web extras
# Enter a provider API key in the UI at runtime, if no CLI key is configured
make start      # launch in the background, http://localhost:8420
make status     # check whether it's up
make logs       # tail logs/web.log
make stop
make restart
make update     # refresh dependencies (and git pull, if this is a git checkout)
make upgrade    # update + restart a running server + health-check
```

The default bind address is `127.0.0.1`, not a public network interface. Override
only the port with `make start PORT=9000` when needed.

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
| `GET  /api/models`          | `provider-specific identifier.MODEL_CATALOG`            |
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

The API key entered in the browser is kept in page memory and included in
individual chat requests. The frontend does not persist it in local storage.
An operator may separately set a persistent key through `POST /api/config`;
that writes to `~/.zcoder-config.json` and should not be used on shared hosts.
The backend masks a configured key in `GET /api/config` responses.

## WSL2 smoke test

Ubuntu users can run `make build PYTHON=/usr/bin/python3` to use the system
Python instead of a separate activated virtual environment. In WSL2, start
the console with `make start HOST=127.0.0.1 PORT=8420`, then open
`http://localhost:8420` in the Windows browser. Verify HTTP connectivity:

```bash
curl -fsS http://127.0.0.1:8420/api/version
curl -fsS http://127.0.0.1:8420/api/health
```

For a real provider acceptance test, enter a valid API key in the UI, select
a model authorized for that key, enable **Streaming**, and ask the model to
reply with `ZCODER_WSL2_OK`. A successful streamed response and a follow-up
answer in the same session confirm provider I/O and in-memory chat history.
The HTTP checks alone do not verify live model access. Provider use may incur
charges.

## Web Console security boundary

This console exposes chat, session history, and local configuration operations.
**It does not provide standalone user authentication or tenant isolation.**
Run it on localhost only. Never expose it directly on a public address or
through a public tunnel. Remote usage requires an independently authenticated
TLS reverse proxy (for example, Cloudflare Access) with strict upstream access
control and an explicit risk review.

Cross-origin browser access is disabled by default. Trusted HTTP Host names
are limited to `localhost` and `127.0.0.1` unless configured explicitly:

```bash
ZCODER_WEB_ALLOWED_HOSTS=localhost,127.0.0.1 \
ZCODER_WEB_CORS_ORIGINS=http://localhost:5173 \
make start HOST=127.0.0.1 PORT=8420
```

`ZCODER_WEB_ALLOWED_HOSTS` accepts exact comma-separated hostnames without
schemes, ports, or wildcards. `ZCODER_WEB_CORS_ORIGINS` accepts explicit HTTP(S)
origins for separate frontend development servers; no wildcard origin is
allowed. **Neither setting provides authentication.**
