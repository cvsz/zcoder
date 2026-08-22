# EP01 — Credential Rotation Closure

**Status:** CLOSED  
**Date:** 2026-08-22  
**Baseline SHA:** `2ec89ce5d3dc060e42fed63d1af156b04c87c0c3` (`main`, version 1.41.0)  
**Owner:** Security / Platform  
**Evidence tier:** E2 (Integration) + E3 (System)

## Scope
Bounded rotation of all long-lived credentials introduced during Upgrade-01..35 and the `src/zcoder` migration (after Upgrade-53 merge `46ad61d7`). Covers provider API keys, GitHub PATs, container registry tokens, signing keys, and `.env` secrets committed to local-only fixtures.

## What was rotated
| Credential class | Old location / risk | Action | New location |
|---|---|---|---|
| `ANTHROPIC_API_KEY` / `VOYAGE_API_KEY` | `.env` committed in dev branches, shell history | Revoked at provider, re-issued via secrets manager | `ZCODER_PROVIDER` env injection, `PYTHON_DOTENV_DISABLED=1` in prod |
| `GITHUB_TOKEN` (PAT) | workflow `permissions: write` broad | Scoped to `contents:read` per `ci.yml:9`, least-privilege | GitHub OIDC + fine-grained PAT per repo |
| GHCR `GITHUB_TOKEN` | container `publish-container.yml` push | Regenerated after `SEC-010.1` pinning (`#84 d6c7280`) | ephemeral `GITHUB_TOKEN` per job |
| GPG signing key (fleet wave 2) | uniform local-key signatures `bced683` | Re-signed 284 commits pass 2, old key revoked | `gpg --list-secret-keys` + attestation in `ep11b-gpg-attestation.md` |
| Postgres `postgres:postgres` CI fixtures | `ci.yml:54-66` ephemeral service | Not rotated (ephemeral) — documented as test-only | — |

## Validation
- `grep -r "ANTHROPIC_API_KEY\|sk-" --include="*.md" --include="*.py"` — no committed secrets; `gitleaks` run `32583958074` green
- `scripts/release_gate.py` → `ProductionReleaseGate` secrets check `PASS` (no high-sensitivity keys on CLI)
- `SECURITY.md:Secrets and credentials` re-verified: env injection only, no history exposure
- Bandit `bandit -r src -ll` green (no B105/B106 hardcoded password)
- Dependency Review green on `316ba22` and `2ec89ce`

## Residual
- Local `~/.config/zcoder/` may still hold developer credentials — out of repo scope, covered by `LOCAL-FREE.md` guidance
- Third-party MCP servers extend trust boundary per `SECURITY.md:Known limitations` — operator review required

## Closure evidence
- Hosted checks on `2ec89ce`: lint `B` clean, bandit `B` clean, CodeQL `B` clean, Dependency Review `B` clean
- `git log --show-signature` uniform `local-key` on `bced683` lineage, verified via `ep11b`
