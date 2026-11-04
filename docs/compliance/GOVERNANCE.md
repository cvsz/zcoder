# Governance

zcoder is maintained with a security-first, bounded-change model.

## Decision authority

The repository owner and designated maintainers are responsible for release policy, security response, architecture boundaries, and final merge decisions. CODEOWNERS identifies default and security-sensitive review ownership.

## Change model

Changes should be delivered as one bounded vertical slice per pull request. A slice must have a concrete problem statement, acceptance criteria, regression coverage, compatibility notes, and the smallest architectural change that solves the confirmed need.

Security findings require source-to-sink validation before remediation. Do not weaken tests, coverage thresholds, permissions, CodeQL, Dependency Review, release gates, or other security controls to obtain a green build.

## Merge policy

A pull request is merge-eligible only when its exact final head has passed every applicable hosted check and has no unresolved blocking review thread. Any code, dependency, workflow, or configuration change after verification invalidates the previous evidence and requires a fresh verification run.

## Release policy

Final release readiness is tracked in `exec-planning.md`. Release candidates must preserve provider-neutral authentication, explicit operator authority for mutating actions, tenant/network/filesystem boundaries, auditable operations, rollback evidence, and supply-chain integrity.

## Security disclosures

Suspected vulnerabilities must follow `SECURITY.md` and should not be discussed in public issues before coordinated remediation or disclosure.

## Changes to governance

Governance changes use the same pull-request and hosted-verification process as code changes. Material changes to ownership, security policy, or release authority should be explicitly called out in the pull request summary.
