# ZeaZDev AI & Engineering Operating Policy

## Read First

This file is the canonical ZeaZDev operating policy for AI agents, coding agents, developers, automation, infrastructure, and repository maintenance.

**Required reading order for every AI/coding agent:**

1. Read this `zeaz.md` completely enough to understand the applicable rules.
2. Read the repository-local `AGENTS.md` and any more-specific instruction files.
3. Inspect the target repository and current state before making changes.
4. Follow the change-safety gate: **Inspect → Understand → Plan → Validate → Apply → Test → Verify → Document**.

## Canonical Source of Truth

- Canonical policy: `cvsz/zeaz/zeaz.md`
- Canonical URL: https://github.com/cvsz/zeaz/blob/main/zeaz.md
- Repository-local instructions may add stricter requirements, but must not silently weaken this policy.
- When this policy changes, dependent repositories should be synchronized and validated.

## Engineering Principles

- Production-grade, complete implementations only; no fake implementations, placeholders, or knowingly broken paths.
- Prefer simple, maintainable designs: **Code is a liability — less is more.**
- Use strong typing and explicit contracts.
- Apply SOLID, Clean Architecture where appropriate, OWASP guidance, secure defaults, least privilege, and defense in depth.
- Validate inputs and handle errors explicitly.
- Design for reproducibility, observability, rollback, and operational ownership.
- Prefer local-first, self-hosted, open-source, and free-tier solutions when they meet requirements; optimize total cost of ownership.

## Change Safety

Before changing production, infrastructure, authentication, DNS, Cloudflare, Terraform, networking, databases, CI/CD, security controls, or shared automation:

- identify the resource, environment, dependencies, and blast radius;
- inspect existing configuration and source of truth;
- preserve working behavior unless a change is explicitly required;
- validate configuration before applying;
- test after applying;
- verify the actual resulting state;
- document material changes and rollback/recovery steps.

Never delete or overwrite merely because something looks obsolete, duplicated, inconsistent, or unused. Investigate first.

## ZeaZDev Infrastructure

The primary domain namespace is `zeaz.dev`.

Cloudflare, DNS, Tunnel, edge security, and related infrastructure should be managed as code with Terraform where applicable. Git is the versioned source of intended configuration; Cloudflare is the execution/edge layer.

Every hostname should be traceable to:

**purpose → repository → service → environment → origin → Cloudflare configuration → Terraform resource → security policy → health check → deployment → rollback**

Unknown, orphaned, duplicate, or conflicting resources are infrastructure debt and require investigation before removal.

## AI Agent Operating Rules

Agents must:

- read `zeaz.md` first;
- read applicable local `AGENTS.md` instructions next;
- inspect before editing;
- search for existing implementations before creating new ones;
- reuse existing abstractions when correct;
- avoid duplicate systems and unnecessary dependencies;
- never claim work was completed unless it was actually performed and verified;
- report uncertainty and blocked validation explicitly;
- keep changes scoped and reviewable;
- update documentation, tests, workflows, and operational metadata when affected.

For destructive or high-impact operations, require an explicit change plan and a reversible path.

## Repository Hygiene

Keep repositories coherent and production-oriented:

- synchronize documentation with implementation;
- keep CI/CD workflows valid;
- keep templates and examples aligned with current behavior;
- remove dead code only after dependency/use analysis;
- do not commit secrets, credentials, tokens, private keys, or generated sensitive data;
- use dependency pinning and automated security/update checks where appropriate;
- preserve license and attribution requirements.

## Validation Standard

A change is not complete merely because a file was edited.

Completion requires, as applicable:

- formatting/linting;
- type checking;
- unit/integration tests;
- build/package validation;
- security checks;
- configuration validation;
- deployment or runtime health checks;
- inspection of the final diff;
- documentation update.

If a required check cannot run, state exactly what could not be verified and why.

## Scope and Precedence

This policy is the ecosystem baseline.

Precedence for instructions is:

1. platform/system safety requirements;
2. applicable repository and path-specific instructions;
3. this ZeaZDev policy;
4. task-specific requirements.

A local instruction may be more restrictive. It must not be used to bypass security, safety, validation, or source-of-truth requirements.

## Repository Rollout

Repositories consuming this policy should place an `AGENTS.md` at their applicable root containing a clear **READ FIRST** reference to this canonical file:

https://github.com/cvsz/zeaz/blob/main/zeaz.md

The local `AGENTS.md` should preserve repository-specific instructions and reference this policy rather than duplicating the complete policy.

## Objective

Build and operate reliable ZeaZDev software and infrastructure with minimal unnecessary complexity, strong security, reproducible delivery, clear ownership, controlled cost, and verifiable production readiness.