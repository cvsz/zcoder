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
4. preserve the Python 3.9–3.12 compatibility matrix until the support policy changes explicitly;
5. keep Ruff, Black, Bandit, Docker, CodeQL, Dependency Review, Release Gate, Helm, and SDK/TypeScript checks independent and visible;
6. never auto-commit broad security remediations from a general-purpose workflow;
7. require exact-head hosted verification before merge;
8. keep published artifact provenance and checksums tied to the release source.

## Dependency automation

Dependabot tracks the repository's Python, GitHub Actions, and Docker ecosystems on a weekly cadence. Minor and patch version updates may be grouped to reduce maintenance noise, but security updates remain subject to normal hosted verification before merge.

Dependabot configuration is not a substitute for Dependency Review on pull requests or CodeQL/Bandit analysis.

## Action versioning

Use maintained major action versions compatible with the current GitHub-hosted runner runtime. Security-sensitive supply-chain hardening should progressively pin third-party actions to immutable full commit SHAs and let Dependabot maintain those references.

Action-major modernization and immutable-SHA pinning are separate concerns: upgrading to a maintained runtime does not by itself provide immutable provenance.

## Helm compatibility

The Helm workflow validates the chart with both the current supported Helm 3 line and Helm 4. This dual validation provides migration evidence while Helm 3 remains security-supported and avoids declaring Helm 4 compatibility based on documentation alone.

## Release provenance

Release workflows generate SHA-256 checksums and GitHub artifact attestations. Container publication also records provenance for the pushed GHCR digest.

The release source must resolve to the requested tag. Manual release dispatch must not silently publish artifacts built from an unrelated branch head.

## One-shot and self-modifying workflows

Temporary repair workflows that rewrite source and push commits are not part of the persistent production workflow set. Once their bounded remediation purpose is complete, remove them rather than leaving a dormant write-capable automation surface in the repository.

## Branch and repository settings

Repository settings such as branch protection/rulesets, required checks, signed commits, merge methods, security features, and environment approvals are operational controls outside source-controlled workflow YAML. Their desired state should be audited as part of final-release qualification and captured as production evidence.

## Future hardening queue

Follow-up supply-chain slices should evaluate:

- immutable full-SHA pinning for third-party and GitHub-maintained actions where practical;
- SBOM generation for Python/container release artifacts;
- OpenSSF Scorecard or equivalent repository-security posture checks;
- release environment approvals and protected tags;
- rulesets requiring exact hosted checks and CODEOWNERS review for security-sensitive paths;
- artifact signature/attestation verification instructions for operators.

These controls should be added as bounded slices and must not bypass existing hosted verification.
