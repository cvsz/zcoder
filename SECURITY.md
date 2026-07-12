# Security Policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public
GitHub issue. Email the maintainer (see repository metadata) with:

- A description of the issue and its impact
- Steps to reproduce, or a PoC if available
- The version/commit affected

We aim to acknowledge reports within 3 business days.

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.16.x  | ✅        |
| < 1.16  | ❌        |

## Built-in security controls

This project ships the following controls (see `security.py`,
`logging_config.py`, `resilience.py`):

- **Path traversal protection** — `security.safe_resolve()` and
  `security.validate_name()` guard every user-supplied path or name
  (project names, artifact names, file uploads/exports) before it touches
  the filesystem.
- **Secret redaction in logs** — `logging_config.RedactingFilter` scrubs
  API-key-shaped strings from every log line before emission, regardless
  of log level or format (JSON/text).
- **Secret-in-output guard** — `security.assert_no_secret()` is available
  for any code path that writes model-generated or user-generated content
  to disk, to catch an API key being echoed back accidentally.
- **URL scheme allow-listing** — `security.validate_url()` rejects
  non-`https` schemes (`file://`, `javascript:`, `data:`, etc.) before a
  URL reaches any fetch/download code path.
- **Input size limits** — `security.check_file_size()` / `MAX_FILE_SIZE_BYTES`
  (default 25 MB, override via `ZCODER_MAX_FILE_SIZE_BYTES`) bound memory
  use from `--file`/`--file-upload` before any API call is made.
- **Least-privilege container** — the Docker image runs as a non-root
  `zcoder` user (see `Dockerfile`); config/cache are volume-mounted under
  that user's home rather than baked into the image.
- **No secrets in the image** — `.dockerignore` excludes `.env`, `.bak`
  files, and git history from the build context.
- **Dependency pinning + scanning** — `requirements.txt` pins a minimum
  `anthropic` SDK version; CI runs `bandit` (static analysis) against the
  full source tree on every push (see `.github/workflows/ci.yml`).
- **Dry-run-by-default destructive operations** — `claude_compliance_api.py`'s
  hard-delete endpoints (chat/file/project) are permanent, org-wide, and
  have no recovery window. Every `cmd_*` that deletes something previews
  what it would do and requires an explicit `--compliance-yes` to actually
  execute, rather than acting on the first invocation.

## Known limitations / out of scope

- **Local code execution**: this CLI does not execute model-generated
  code locally. `claude_sandbox.py` and `claude_code_exec.py` delegate to
  Anthropic's hosted code-execution tool. If you extend this project to
  run generated code locally, that requires its own sandboxing (containers,
  seccomp, no network) which is *not* provided here.
- **API key storage**: `~/.ai-coder-config.json` stores the key in plain
  text on disk if you use `--setup` instead of an environment variable.
  Prefer `ANTHROPIC_API_KEY` (env var, or a secrets manager in production)
  over the on-disk config for anything beyond local dev.
- **Rate limiting is client-side only**: `resilience.py`'s retry/circuit
  breaker protect *this process* from hammering a struggling API; they are
  not a substitute for server-side rate limiting if you expose this tool
  behind a shared service.
- **Admin/Compliance keys have a much larger blast radius than a regular
  API key**: `--admin-api-key` and `--compliance-api-key` (and their
  `ANTHROPIC_ADMIN_API_KEY` / `ANTHROPIC_COMPLIANCE_API_KEY` env-var
  equivalents) follow the same plain-text-on-disk-if-you-use-`--setup`
  handling as the regular API key above, but a leaked Compliance Access
  Key can read or hard-delete *any user's* chats and files org-wide, not
  just this CLI session's. Treat these as higher-sensitivity secrets than
  `ANTHROPIC_API_KEY` — prefer an env var or secrets manager, not
  `--compliance-api-key`/`--admin-api-key` on the command line where
  shell history or `ps` can leak it.
