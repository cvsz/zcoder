# EP11b — GPG Attestation Closure

**Status:** CLOSED  
**Date:** 2026-08-22  
**Baseline:** `2ec89ce` (descends from `bced683` history re-signing pass 2, 284 commits)  
**Key:** local-key uniform signatures (see `git log --show-signature`)  
**Evidence tier:** E2 + compliance `CONTROL-CATALOG.md`

## Scope
Prove that the full-history re-signing (Upgrade-53 post-merge `46ad61d7` → `2a8adcf` src-layout migration → `bced683` pass 2) is attested and that release artifacts are verifiable.

## History re-signing
- Pass 2: `bced683 docs: record history re-signing pass 2 (284 commits, uniform local-key signatures)`
- Verification:
  ```
  git log --oneline --show-signature bced683^..2ec89ce | grep -c "Good signature"
  # 284 + 5 (post-pass) = 289
  gpg --verify-commit 2ec89ce
  ```
- Old key revoked per `ep01-credential-rotation.md`; new key `local-key` is the sole signer from `bced683` onward

## Release attestation
| Artifact | Provenance | Verification |
|---|---|---|
| `dist/zcoder-1.41.0-py3-none-any.whl` | `uv build` + `gh attestation` (Sigstore) | `gh attestation verify dist/* --repo cvsz/zcoder` |
| `ghcr.io/cvsz/zcoder:1.41.0` | `publish-container.yml` OIDC + `anchore/sbom-action` | `cosign verify ghcr.io/cvsz/zcoder:1.41.0` + `syft` SBOM |
| `uv.lock` + `pyproject.toml` | reproducible-build `reproducibility.yml` | `uv lock --check` clean |
| Git tag `v1.41.0` | `release.yml` tag `refs/tags/v1.41.0` | `git verify-tag v1.41.0` |

## Checks on `2ec89ce`
- `release_gate.py` → `ProductionReleaseGate` attestation check `PASS`
- `security-scan.yml` + `dependency-review.yml` + `codeql.yml` all green on `316ba22`→`2ec89ce` lineage
- `ROADMAP-NEXT.md` liveness fixed — no longer references stale PR #6 / hardening branch

## Residual
- Branch protection still `protected: false` on `main` per earlier audit — requires `docs/operations/GITHUB-GOVERNANCE.md:Future hardening queue` rulesets (separate slice, not blocking GPG closure)
- Helm chart provenance `Chart.yaml` version `1.41.0` aligns with app version

## Closure
GPG history and release attestation are **closed** on `2ec89ce`. Revocation/rotation procedure documented in `ep01`.
