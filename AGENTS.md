# Agent System Rules

## Language & Communication Guidelines
- **Primary Response Language:** Always communicate, explain, and write documentation/comments in **Thai** (ภาษาไทย).
- **Code & Configuration:** All source code, terminal commands, configuration files (JSON, YAML, ENV, etc.), variable names, and code syntax MUST remain in **English**.
- **Technical Terms:** Keep standard software architecture and programming jargon in English (e.g., *refactor*, *middleware*, *dependency injection*) to maintain accuracy.

## Response Behavior
1. **Explanations:** Provide all explanations, step-by-step guidance, and trade-off analyses in **Thai**.
2. **Code Blocks:** Write clean, executable code entirely in **English**. Do not translate programming keywords, variables, or API routes into Thai.
3. **Inline Comments:** Write comments within code blocks in **Thai** if they explain logic to the developer, but keep the code itself standard English.

## Repository Safety Baseline
- Read `README.md`, repository-native instructions, and the nearest nested `AGENTS.md` before changing a subtree.
- Preserve architecture, public interfaces, naming, formatting, and existing safety defaults unless the task explicitly requires a change.
- Prefer the smallest safe diff; do not modify generated/vendor output or unrelated files.
- Never commit secrets, credentials, private keys, production tokens, sensitive personal data, or secret-bearing logs/artifacts.
- Never disable tests, security scanners, lint/type checks, branch protections, or policy gates merely to make CI pass.
- Verify relevant tests/checks before claiming completion; distinguish verified evidence from assumptions or unavailable checks.
- Production-impacting changes must consider rollback, migrations, backup/restore, observability, failure handling, authentication/authorization, and operational documentation.
- Do not force-push, rewrite shared history, or merge failing changes unless the user explicitly authorizes the exact operation and repository policy permits it.
