# GitHub Governance and Workflow Policy

This document describes the repository-level GitHub controls used to keep zcoder changes bounded, reviewable, reproducible, and release-ready.

## Community health and contribution surfaces

The repository maintains:

- `.github/PULL_REQUEST_TEMPLATE.md` for bounded change, validation, security, rollback, and documentation evidence;
- structured bug and feature issue forms under `.github/ISSUE_TEMPLATE/`;
- `.github/CODEOWNERS` for default and security-sensitive review ownership;
- root `GOVERNANCE.md`, `SUPPORT.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, and `CONTRIBUTING.md`.

Security vulnerabilities must use the private reporting path described in `SECURITY.md`; public issue forms explicitly reject vulnerability disclosure.

## Workflow principles

Every workflow should follow these rules:

1. declare the minimum `permissions` required by the job;
2. use bounded `timeout-minutes` for non-trivial jobs;
3. use concurrency controls where duplicate pull-request work can be cancelled safely;
4. keep the supported Python versions aligned with `project.requires-python` and the CI matrix (currently Python 3.12 and 3.13);
5. keep Ruff, Black, Bandit, Docker, CodeQL, Dependency Review, Release Gate, Helm, and SDK/TypeScript checks independent and visible;
6. never auto-commit broad security remediations from a general-purpose workflow;
7. require exact-head hosted verification before merge;
8. keep published artifact provenance and checksums tied to the release source.

## Dependency automation

Dependabot tracks the repository's Python, GitHub Actions, and Docker ecosystems on a weekly cadence. Minor and patch version updates may be grouped to reduce maintenance noise, but security updates remain subject to normal hosted verification before merge.

Dependabot configuration is not a substitute for Dependency Review on pull requests or CodeQL/Bandit analysis.

## Action versioning

Use maintained major action versions compatible with the current GitHub-hosted runner runtime. All workflow `uses:` refs are pinned to immutable full commit SHAs (completed in PR #84, SEC-010.1), with version-tag comments preserved so Dependabot continues to maintain the pins.

Action-major modernization and immutable-SHA pinning are separate concerns: upgrading to a maintained runtime does not by itself provide immutable provenance.

## Helm compatibility

The Helm workflow validates the chart with both the current supported Helm 3 line and Helm 4. This dual validation provides migration evidence while Helm 3 remains security-supported and avoids declaring Helm 4 compatibility based on documentation alone.

## Release provenance

Release workflows generate SHA-256 checksums and GitHub artifact attestations. Container publication also records provenance for the pushed GHCR digest.

The release source must resolve to the requested tag. Manual release dispatch must not silently publish artifacts built from an unrelated branch head.

The local release gate ignores hosted evidence while the worktree is dirty. Hosted CI evidence alone cannot qualify PITR: production qualification also requires a JSON record in the Actions repository variable `ZCODER_PITR_EVIDENCE_JSON`, bound to the exact candidate SHA, with `schema: 1`, `wal_archive_verified: true`, `restore_drill_passed: true`, a UTC `tested_at` within the last 30 days, a sanitized `evidence_ref`, and the 64-character `evidence_sha256` of the referenced operational record. Set the variable after the candidate commit is created and before tagging it; a candidate-bound record must not be committed into that same candidate because doing so changes its SHA. Never put credentials, DSNs, backup contents, or personal data in the record. The reference must resolve to an independently reviewable operational record showing the production WAL target and a successful restore drill.

## One-shot and self-modifying workflows

Temporary repair workflows that rewrite source and push commits are not part of the persistent production workflow set. Once their bounded remediation purpose is complete, remove them rather than leaving a dormant write-capable automation surface in the repository.

## CI repair orchestration

`GitHubOrchestrator.execute_ci_repair_loop()` reports success only when the provider returns completed successful checks for the observed pull-request head. Failed checks require an explicitly configured repair handler; after it reports a repair, the orchestrator reloads the pull request and verifies that its head SHA changed before checking the new revision. Missing or pending checks, missing repair configuration, handler failure, an unchanged head, or unsuccessful checks fail closed. The orchestration layer does not create synthetic commits or CI results.

## Branch and repository settings

Repository settings such as branch protection/rulesets, required checks, signed commits, merge methods, security features, and environment approvals are operational controls outside source-controlled workflow YAML. Their desired state should be audited as part of final-release qualification and captured as production evidence. On 2026-10-25, the live `main` protection required-check matrix was reconciled to the CI Python 3.12/3.13 matrix: obsolete `test (3.10)` and `test (3.11)` contexts were removed and `test (3.13)` was added. Strict checks, one required approval, admin enforcement, and disabled force-push/deletion remained enabled after the update. Re-query the live policy and exact-head hosted checks before release because these settings and results can drift.

## Future hardening queue

Follow-up supply-chain slices should evaluate:

- ~~immutable full-SHA pinning for third-party and GitHub-maintained actions~~ — DONE (PR #84);
- SBOM generation for Python/container release artifacts;
- OpenSSF Scorecard or equivalent repository-security posture checks;
- release environment approvals and protected tags;
- rulesets requiring exact hosted checks and CODEOWNERS review for security-sensitive paths;
- artifact signature/attestation verification instructions for operators.

These controls should be added as bounded slices and must not bypass existing hosted verification.
